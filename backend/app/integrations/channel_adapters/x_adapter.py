import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.domain.models.channel import Channel
from app.domain.models.channel import ChannelType
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

X_TOKEN_URL = "https://api.x.com/2/oauth2/token"
X_ME_URL = "https://api.x.com/2/users/me"
X_CREATE_POST_URL = "https://api.x.com/2/tweets"


class XAdapter(BaseChannelAdapter):
    channel_type = ChannelType.X.value

    def __init__(self, db: Session) -> None:
        self.db = db
        self._current_post: Post | None = None
        self._active_access_token: str | None = None

    @classmethod
    def get_capabilities(cls) -> dict:
        return {
            "text": True,
            "image": False,
            "video": False,
            "reels": False,
            "shorts": False,
            "max_length": 280,
        }

    async def publish_post(self, *, post: Post, channel: Channel) -> dict:
        self._current_post = post
        self._active_access_token = None
        return await super().publish_post(post=post, channel=channel)

    async def validate_credentials(self) -> None:
        if self._current_post is None:
            raise AdapterAuthError("X adapter context missing post")
        account = load_platform_account(self.db, company_id=self._current_post.company_id, platform=self.channel_type)
        if account is None:
            raise AdapterAuthError("X account not connected for tenant")

        if is_token_expiring(account, within_seconds=90):
            self._active_access_token = await self._refresh_access_token()
        else:
            self._active_access_token = decrypted_access_token(account)

        if not self._active_access_token:
            raise AdapterAuthError("X access token unavailable")

        headers = {"Authorization": f"Bearer {self._active_access_token}"}
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(X_ME_URL, headers=headers)
            if response.status_code == 401:
                raise AdapterAuthError("X access token is invalid or expired")
            if response.status_code == 403:
                raise AdapterAuthError("X API permission denied")
            if response.status_code >= 500:
                raise AdapterRetryableError("X API unavailable during credential validation")
            if response.status_code >= 400:
                raise AdapterPermanentError(f"X credential validation failed: {response.status_code}")

    async def refresh_credentials(self) -> None:
        self._active_access_token = await self._refresh_access_token()

    async def publish_text(self, *, post: Post, channel: Channel) -> dict:
        access_token = self._active_access_token
        if not access_token:
            await self.validate_credentials()
            access_token = self._active_access_token
        if not access_token:
            raise AdapterAuthError("X access token unavailable")

        max_length = int(self.get_capabilities().get("max_length", 280))
        text = f"{post.title}\n\n{post.content}".strip()
        if len(text) > max_length:
            text = text[: max_length - 3] + "..."

        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(X_CREATE_POST_URL, headers=headers, json={"text": text})
            if response.status_code == 401:
                raise AdapterAuthError("X publish unauthorized")
            if response.status_code == 403:
                raise AdapterAuthError("X publish forbidden (missing tweet.write/users.read scope)")
            if response.status_code == 429 or response.status_code >= 500:
                raise AdapterRetryableError(f"X publish temporary failure: {response.status_code}")
            if response.status_code >= 400:
                raise AdapterPermanentError(f"X publish failed: {response.status_code} {response.text}")
            payload = response.json()

        data = payload.get("data") or {}
        external_post_id = str(data.get("id") or "")
        if not external_post_id:
            raise AdapterPermanentError("X publish response missing post id")

        return {
            "external_post_id": external_post_id,
            "channel_type": self.channel_type,
            "platform": self.channel_type,
        }

    async def publish_media(self, *, post: Post, channel: Channel) -> dict:
        result = await self.publish_text(post=post, channel=channel)
        media_reference = self._extract_media_reference(post)
        if media_reference:
            result["warning"] = "X media upload is not enabled in this phase. Published as text-only."
            result["media_source_url"] = media_reference
        return result

    async def _refresh_access_token(self) -> str:
        if self._current_post is None:
            raise AdapterAuthError("X adapter context missing post")
        account = load_platform_account(self.db, company_id=self._current_post.company_id, platform=self.channel_type)
        if account is None:
            raise AdapterAuthError("X account not connected for tenant")
        refresh_token = decrypted_refresh_token(account)
        if not refresh_token:
            raise AdapterAuthError("X refresh token not available")
        if not settings.x_client_id or not settings.x_client_secret:
            raise AdapterAuthError("X OAuth client configuration missing")

        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": settings.x_client_id,
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                X_TOKEN_URL,
                data=data,
                headers=headers,
                auth=(settings.x_client_id, settings.x_client_secret),
            )
            if response.status_code == 401:
                raise AdapterAuthError("X refresh token unauthorized")
            if response.status_code == 403:
                raise AdapterAuthError("X refresh token forbidden")
            if response.status_code >= 500:
                raise AdapterRetryableError("X token refresh temporary failure")
            if response.status_code >= 400:
                raise AdapterAuthError(f"X token refresh failed: {response.status_code} {response.text}")
            payload = response.json()

        access_token = str(payload.get("access_token") or "")
        if not access_token:
            raise AdapterAuthError("X token refresh response missing access token")
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
