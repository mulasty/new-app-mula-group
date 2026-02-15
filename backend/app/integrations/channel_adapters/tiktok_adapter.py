import asyncio

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.domain.models.channel import Channel, ChannelType
from app.domain.models.post import Post
from app.integrations.channel_adapters.base_adapter import (
    AdapterAuthError,
    AdapterPermanentError,
    AdapterRetryableError,
    BaseChannelAdapter,
)
from app.integrations.channel_adapters.social_account_utils import (
    decrypted_access_token,
    decrypted_refresh_token,
    is_token_expiring,
    load_platform_account,
    persist_tokens,
)
from app.integrations.media_upload_service import upload_media

TIKTOK_TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
TIKTOK_CREATOR_INFO_URL = "https://open.tiktokapis.com/v2/post/publish/creator_info/query/"
TIKTOK_CONTENT_INIT_URL = "https://open.tiktokapis.com/v2/post/publish/content/init/"
TIKTOK_STATUS_FETCH_URL = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"


class TikTokAdapter(BaseChannelAdapter):
    channel_type = ChannelType.TIKTOK.value

    def __init__(self, db: Session) -> None:
        self.db = db
        self._current_post: Post | None = None
        self._active_access_token: str | None = None

    @classmethod
    def get_capabilities(cls) -> dict:
        return {
            "text": False,
            "image": False,
            "video": True,
            "reels": False,
            "shorts": True,
            "max_length": 2200,
        }

    async def publish_post(self, *, post: Post, channel: Channel) -> dict:
        self._current_post = post
        self._active_access_token = None
        return await super().publish_post(post=post, channel=channel)

    async def validate_credentials(self) -> None:
        if self._current_post is None:
            raise AdapterAuthError("TikTok adapter context missing post")

        account = load_platform_account(self.db, company_id=self._current_post.company_id, platform=self.channel_type)
        if account is None:
            raise AdapterAuthError("TikTok account not connected for tenant")

        if is_token_expiring(account, within_seconds=90):
            self._active_access_token = await self._refresh_access_token()
        else:
            self._active_access_token = decrypted_access_token(account)
        if not self._active_access_token:
            raise AdapterAuthError("TikTok access token unavailable")

        headers = {
            "Authorization": f"Bearer {self._active_access_token}",
            "Content-Type": "application/json; charset=UTF-8",
        }
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(TIKTOK_CREATOR_INFO_URL, headers=headers, json={})
            if response.status_code in {401, 403}:
                raise AdapterAuthError("TikTok token unauthorized for creator_info")
            if response.status_code >= 500:
                raise AdapterRetryableError("TikTok API unavailable during credential validation")
            if response.status_code >= 400:
                raise AdapterPermanentError(f"TikTok creator_info query failed: {response.status_code}")
            payload = response.json()
            error = payload.get("error") or {}
            if error and error.get("code") not in {"ok", None}:
                code = str(error.get("code") or "")
                message = str(error.get("message") or "unknown")
                if "scope" in code.lower() or "auth" in code.lower():
                    raise AdapterAuthError(f"TikTok permission error: {message}")
                raise AdapterPermanentError(f"TikTok creator_info rejected: {code} {message}")

    async def refresh_credentials(self) -> None:
        self._active_access_token = await self._refresh_access_token()

    async def publish_text(self, *, post: Post, channel: Channel) -> dict:
        raise AdapterPermanentError("TikTok publish requires video media URL")

    async def publish_media(self, *, post: Post, channel: Channel) -> dict:
        access_token = self._active_access_token
        if not access_token:
            await self.validate_credentials()
            access_token = self._active_access_token
        if not access_token:
            raise AdapterAuthError("TikTok access token unavailable")

        media_reference = self._extract_media_reference(post)
        if not media_reference:
            raise AdapterPermanentError("TikTok publish requires a video URL in post content")
        if not media_reference.lower().endswith((".mp4", ".mov", ".m4v", ".webm")):
            raise AdapterPermanentError("TikTok connector currently supports video URL publishing only")

        media = await upload_media(self.channel_type, media_reference)
        caption = f"{post.title}\n\n{post.content}".strip()[:2200]
        payload = {
            "post_info": {
                "title": caption,
                "privacy_level": "PUBLIC_TO_EVERYONE",
                "disable_comment": False,
                "disable_duet": False,
                "disable_stitch": False,
            },
            "source_info": {
                "source": "PULL_FROM_URL",
                "video_url": media["source_url"],
            },
        }
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
        }
        async with httpx.AsyncClient(timeout=25.0) as client:
            response = await client.post(TIKTOK_CONTENT_INIT_URL, headers=headers, json=payload)
            if response.status_code in {401, 403}:
                raise AdapterAuthError("TikTok publish unauthorized")
            if response.status_code == 429 or response.status_code >= 500:
                raise AdapterRetryableError(f"TikTok publish init temporary failure: {response.status_code}")
            if response.status_code >= 400:
                raise AdapterPermanentError(f"TikTok publish init failed: {response.status_code} {response.text}")
            init_payload = response.json()

        init_error = init_payload.get("error") or {}
        if init_error and init_error.get("code") not in {"ok", None}:
            code = str(init_error.get("code") or "")
            message = str(init_error.get("message") or "unknown")
            if "scope" in code.lower() or "auth" in code.lower():
                raise AdapterAuthError(f"TikTok publish init auth error: {message}")
            if code.lower().startswith("internal"):
                raise AdapterRetryableError(f"TikTok publish init temporary error: {message}")
            raise AdapterPermanentError(f"TikTok publish init rejected: {code} {message}")

        data = init_payload.get("data") or {}
        publish_id = str(data.get("publish_id") or "")
        if not publish_id:
            raise AdapterPermanentError("TikTok publish init response missing publish_id")

        status_payload = await self._poll_publish_status(access_token=access_token, publish_id=publish_id)
        warning = None
        status_value = str(((status_payload.get("data") or {}).get("status") or "")).upper()
        if status_value in {"SEND_TO_USER_INBOX", "INBOX_SHARE"}:
            warning = "TikTok unaudited/inbox flow: creator must complete post in TikTok app."

        return {
            "external_post_id": publish_id,
            "publish_id": publish_id,
            "channel_type": self.channel_type,
            "platform": self.channel_type,
            "media": media,
            "status_payload": status_payload,
            "warning": warning,
        }

    async def _poll_publish_status(self, *, access_token: str, publish_id: str) -> dict:
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
        }
        payload = {"publish_id": publish_id}
        terminal_success = {"PUBLISH_COMPLETE", "PUBLISHED", "INBOX_SHARE", "SEND_TO_USER_INBOX"}
        terminal_failed = {"FAILED", "ERROR", "PUBLISH_FAILED"}
        last_payload: dict = {}

        async with httpx.AsyncClient(timeout=20.0) as client:
            for _ in range(6):
                response = await client.post(TIKTOK_STATUS_FETCH_URL, headers=headers, json=payload)
                if response.status_code in {401, 403}:
                    raise AdapterAuthError("TikTok publish status unauthorized")
                if response.status_code == 429 or response.status_code >= 500:
                    raise AdapterRetryableError("TikTok publish status temporary failure")
                if response.status_code >= 400:
                    raise AdapterPermanentError(
                        f"TikTok publish status query failed: {response.status_code} {response.text}"
                    )
                last_payload = response.json()
                error = last_payload.get("error") or {}
                if error and error.get("code") not in {"ok", None}:
                    code = str(error.get("code") or "")
                    if "token" in code.lower() or "scope" in code.lower():
                        raise AdapterAuthError(f"TikTok status auth error: {code}")
                    if "internal" in code.lower():
                        raise AdapterRetryableError(f"TikTok status temporary error: {code}")
                    raise AdapterPermanentError(f"TikTok status failed: {code}")

                status_value = str(((last_payload.get("data") or {}).get("status") or "")).upper()
                if status_value in terminal_success:
                    return last_payload
                if status_value in terminal_failed:
                    raise AdapterPermanentError(f"TikTok publish failed with status: {status_value}")
                await asyncio.sleep(5)

        return last_payload

    async def _refresh_access_token(self) -> str:
        if self._current_post is None:
            raise AdapterAuthError("TikTok adapter context missing post")
        account = load_platform_account(self.db, company_id=self._current_post.company_id, platform=self.channel_type)
        if account is None:
            raise AdapterAuthError("TikTok account not connected for tenant")
        refresh_token = decrypted_refresh_token(account)
        if not refresh_token:
            raise AdapterAuthError("TikTok refresh token not available")
        if not settings.tiktok_client_key or not settings.tiktok_client_secret:
            raise AdapterAuthError("TikTok OAuth client configuration missing")

        data = {
            "client_key": settings.tiktok_client_key,
            "client_secret": settings.tiktok_client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(TIKTOK_TOKEN_URL, data=data, headers=headers)
            if response.status_code in {401, 403}:
                raise AdapterAuthError("TikTok refresh token unauthorized")
            if response.status_code >= 500:
                raise AdapterRetryableError("TikTok token refresh temporary failure")
            if response.status_code >= 400:
                raise AdapterAuthError(f"TikTok token refresh failed: {response.status_code} {response.text}")
            payload = response.json()

        error = payload.get("error") or {}
        if error and error.get("code") not in {"ok", None}:
            raise AdapterAuthError(f"TikTok token refresh rejected: {error.get('code')}")

        access_token = str(payload.get("access_token") or "")
        if not access_token:
            raise AdapterAuthError("TikTok refresh response missing access token")
        refresh_token_next = str(payload.get("refresh_token") or refresh_token)
        expires_in = int(payload.get("expires_in", 3600))
        persist_tokens(
            self.db,
            account=account,
            access_token=access_token,
            refresh_token=refresh_token_next,
            expires_in_seconds=expires_in,
        )
        return access_token
