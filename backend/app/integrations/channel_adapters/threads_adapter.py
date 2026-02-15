import httpx
from sqlalchemy.orm import Session

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
    is_token_expiring,
    load_platform_account,
    persist_tokens,
)
from app.integrations.media_upload_service import upload_media

THREADS_ME_URL = "https://graph.threads.net/v1.0/me"
THREADS_CREATE_URL_TEMPLATE = "https://graph.threads.net/v1.0/{threads_user_id}/threads"
THREADS_PUBLISH_URL_TEMPLATE = "https://graph.threads.net/v1.0/{threads_user_id}/threads_publish"
THREADS_REFRESH_URL = "https://graph.threads.net/refresh_access_token"


class ThreadsAdapter(BaseChannelAdapter):
    channel_type = ChannelType.THREADS.value

    def __init__(self, db: Session) -> None:
        self.db = db
        self._current_post: Post | None = None
        self._active_access_token: str | None = None

    @classmethod
    def get_capabilities(cls) -> dict:
        return {
            "text": True,
            "image": True,
            "video": True,
            "reels": False,
            "shorts": False,
            "max_length": 500,
        }

    async def publish_post(self, *, post: Post, channel: Channel) -> dict:
        self._current_post = post
        self._active_access_token = None
        return await super().publish_post(post=post, channel=channel)

    async def validate_credentials(self) -> None:
        if self._current_post is None:
            raise AdapterAuthError("Threads adapter context missing post")

        account = load_platform_account(self.db, company_id=self._current_post.company_id, platform=self.channel_type)
        if account is None:
            raise AdapterAuthError("Threads account not connected for tenant")

        if is_token_expiring(account, within_seconds=90):
            self._active_access_token = await self._refresh_access_token()
        else:
            self._active_access_token = decrypted_access_token(account)
        if not self._active_access_token:
            raise AdapterAuthError("Threads access token unavailable")

        params = {"fields": "id,username", "access_token": self._active_access_token}
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(THREADS_ME_URL, params=params)
            if response.status_code == 401:
                raise AdapterAuthError("Threads access token unauthorized")
            if response.status_code == 403:
                raise AdapterAuthError("Threads permission denied")
            if response.status_code >= 500:
                raise AdapterRetryableError("Threads API unavailable during credential validation")
            if response.status_code >= 400:
                raise AdapterPermanentError(f"Threads credential validation failed: {response.status_code}")

    async def refresh_credentials(self) -> None:
        self._active_access_token = await self._refresh_access_token()

    async def publish_text(self, *, post: Post, channel: Channel) -> dict:
        access_token = self._active_access_token
        if not access_token:
            await self.validate_credentials()
            access_token = self._active_access_token
        if not access_token:
            raise AdapterAuthError("Threads access token unavailable")

        account = load_platform_account(self.db, company_id=post.company_id, platform=self.channel_type)
        if account is None:
            raise AdapterAuthError("Threads account not connected for tenant")
        threads_user_id = account.external_account_id

        caption = f"{post.title}\n\n{post.content}".strip()
        create_payload = {"media_type": "TEXT", "text": caption, "access_token": access_token}
        creation_id = await self._create_media_container(threads_user_id=threads_user_id, payload=create_payload)
        published_id = await self._publish_container(
            threads_user_id=threads_user_id,
            creation_id=creation_id,
            access_token=access_token,
        )
        return {
            "external_post_id": published_id,
            "creation_id": creation_id,
            "channel_type": self.channel_type,
            "platform": self.channel_type,
        }

    async def publish_media(self, *, post: Post, channel: Channel) -> dict:
        access_token = self._active_access_token
        if not access_token:
            await self.validate_credentials()
            access_token = self._active_access_token
        if not access_token:
            raise AdapterAuthError("Threads access token unavailable")

        account = load_platform_account(self.db, company_id=post.company_id, platform=self.channel_type)
        if account is None:
            raise AdapterAuthError("Threads account not connected for tenant")
        threads_user_id = account.external_account_id

        media_reference = self._extract_media_reference(post)
        if not media_reference:
            return await self.publish_text(post=post, channel=channel)
        media = await upload_media(self.channel_type, media_reference)
        caption = f"{post.title}\n\n{post.content}".strip()
        media_type = "VIDEO" if media_reference.lower().endswith((".mp4", ".mov", ".m4v")) else "IMAGE"
        media_field = "video_url" if media_type == "VIDEO" else "image_url"
        create_payload = {
            "media_type": media_type,
            media_field: media["source_url"],
            "text": caption,
            "access_token": access_token,
        }
        creation_id = await self._create_media_container(threads_user_id=threads_user_id, payload=create_payload)
        published_id = await self._publish_container(
            threads_user_id=threads_user_id,
            creation_id=creation_id,
            access_token=access_token,
        )
        return {
            "external_post_id": published_id,
            "creation_id": creation_id,
            "channel_type": self.channel_type,
            "platform": self.channel_type,
            "media": media,
        }

    async def _create_media_container(self, *, threads_user_id: str, payload: dict) -> str:
        url = THREADS_CREATE_URL_TEMPLATE.format(threads_user_id=threads_user_id)
        async with httpx.AsyncClient(timeout=25.0) as client:
            response = await client.post(url, data=payload)
            if response.status_code == 401:
                raise AdapterAuthError("Threads create container unauthorized")
            if response.status_code == 403:
                raise AdapterAuthError("Threads create container forbidden")
            if response.status_code == 429 or response.status_code >= 500:
                raise AdapterRetryableError(f"Threads create container temporary failure: {response.status_code}")
            if response.status_code >= 400:
                raise AdapterPermanentError(
                    f"Threads create container failed: {response.status_code} {response.text}"
                )
            data = response.json()

        creation_id = str(data.get("id") or "")
        if not creation_id:
            raise AdapterPermanentError("Threads create container response missing id")
        return creation_id

    async def _publish_container(self, *, threads_user_id: str, creation_id: str, access_token: str) -> str:
        url = THREADS_PUBLISH_URL_TEMPLATE.format(threads_user_id=threads_user_id)
        payload = {"creation_id": creation_id, "access_token": access_token}
        async with httpx.AsyncClient(timeout=25.0) as client:
            response = await client.post(url, data=payload)
            if response.status_code == 401:
                raise AdapterAuthError("Threads publish unauthorized")
            if response.status_code == 403:
                raise AdapterAuthError("Threads publish forbidden")
            if response.status_code == 429 or response.status_code >= 500:
                raise AdapterRetryableError(f"Threads publish temporary failure: {response.status_code}")
            if response.status_code >= 400:
                raise AdapterPermanentError(f"Threads publish failed: {response.status_code} {response.text}")
            data = response.json()

        external_post_id = str(data.get("id") or "")
        if not external_post_id:
            raise AdapterPermanentError("Threads publish response missing id")
        return external_post_id

    async def _refresh_access_token(self) -> str:
        if self._current_post is None:
            raise AdapterAuthError("Threads adapter context missing post")
        account = load_platform_account(self.db, company_id=self._current_post.company_id, platform=self.channel_type)
        if account is None:
            raise AdapterAuthError("Threads account not connected for tenant")
        access_token = decrypted_access_token(account)
        if not access_token:
            raise AdapterAuthError("Threads access token unavailable")

        params = {"grant_type": "th_refresh_token", "access_token": access_token}
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(THREADS_REFRESH_URL, params=params)
            if response.status_code in {401, 403}:
                raise AdapterAuthError("Threads token refresh denied")
            if response.status_code >= 500:
                raise AdapterRetryableError("Threads token refresh temporary failure")
            if response.status_code >= 400:
                raise AdapterAuthError(f"Threads token refresh failed: {response.status_code}")
            payload = response.json()

        refreshed_access_token = str(payload.get("access_token") or "")
        if not refreshed_access_token:
            raise AdapterAuthError("Threads refresh response missing access token")
        expires_in = int(payload.get("expires_in", 3600))
        persist_tokens(
            self.db,
            account=account,
            access_token=refreshed_access_token,
            refresh_token=None,
            expires_in_seconds=expires_in,
        )
        return refreshed_access_token
