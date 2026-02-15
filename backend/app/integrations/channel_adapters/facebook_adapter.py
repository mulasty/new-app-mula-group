import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import decrypt_secret
from app.domain.models.channel import Channel
from app.domain.models.post import Post
from app.integrations.channel_adapters.base_adapter import (
    AdapterAuthError,
    AdapterPermanentError,
    AdapterRetryableError,
    BaseChannelAdapter,
)
from app.integrations.channel_adapters.meta_token_service import (
    ensure_valid_facebook_user_token,
    parse_meta_error,
    pick_facebook_page,
)
from app.integrations.media_upload_service import upload_media


class FacebookAdapter(BaseChannelAdapter):
    channel_type = "facebook"

    def __init__(self, db: Session) -> None:
        self.db = db
        self._current_post: Post | None = None
        self._current_channel: Channel | None = None

    @classmethod
    def get_capabilities(cls) -> dict:
        return {
            "text": True,
            "image": True,
            "video": True,
            "reels": True,
            "shorts": False,
            "max_length": 63206,
        }

    async def publish_post(self, *, post: Post, channel: Channel) -> dict:
        self._current_post = post
        self._current_channel = channel
        return await super().publish_post(post=post, channel=channel)

    async def validate_credentials(self) -> None:
        if self._current_post is None:
            raise AdapterAuthError("Facebook adapter context missing post")
        try:
            await ensure_valid_facebook_user_token(self.db, self._current_post.company_id)
        except ValueError as exc:
            raise AdapterAuthError(str(exc)) from exc

    async def refresh_credentials(self) -> None:
        if self._current_post is None:
            raise AdapterAuthError("Facebook adapter context missing post")
        try:
            await ensure_valid_facebook_user_token(self.db, self._current_post.company_id)
        except ValueError as exc:
            raise AdapterAuthError(str(exc)) from exc

    async def publish_text(self, *, post: Post, channel: Channel) -> dict:
        page = pick_facebook_page(self.db, company_id=post.company_id, preferred_channel_name=channel.name)
        message = f"{post.title}\n\n{post.content}".strip()

        data = {
            "message": message,
            "access_token": decrypt_secret(page.access_token),
        }

        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(f"{settings.meta_graph_api_base_url}/{page.page_id}/feed", data=data)
            if response.status_code >= 400:
                payload = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
                if response.status_code in {401, 403}:
                    raise AdapterAuthError(f"Facebook publish unauthorized: {parse_meta_error(payload)}")
                if response.status_code == 429 or response.status_code >= 500:
                    raise AdapterRetryableError(f"Facebook publish temporary failure: {parse_meta_error(payload)}")
                raise AdapterPermanentError(f"Facebook publish failed: {parse_meta_error(payload)}")
            payload = response.json()

        external_post_id = str(payload.get("id") or "")
        if not external_post_id:
            raise AdapterPermanentError("Facebook publish response missing post id")

        return {
            "external_post_id": external_post_id,
            "channel_type": self.channel_type,
            "platform": self.channel_type,
            "page_id": page.page_id,
            "page_name": page.page_name,
        }

    async def publish_media(self, *, post: Post, channel: Channel) -> dict:
        media_reference = self._extract_media_reference(post)
        if not media_reference:
            return await self.publish_text(post=post, channel=channel)

        page = pick_facebook_page(self.db, company_id=post.company_id, preferred_channel_name=channel.name)
        media = await upload_media(self.channel_type, media_reference)
        data = {
            "message": f"{post.title}\n\n{post.content}".strip(),
            "link": media["source_url"],
            "access_token": decrypt_secret(page.access_token),
        }
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(f"{settings.meta_graph_api_base_url}/{page.page_id}/feed", data=data)
            if response.status_code >= 400:
                payload = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
                if response.status_code in {401, 403}:
                    raise AdapterAuthError(f"Facebook media publish unauthorized: {parse_meta_error(payload)}")
                if response.status_code == 429 or response.status_code >= 500:
                    raise AdapterRetryableError(
                        f"Facebook media publish temporary failure: {parse_meta_error(payload)}"
                    )
                raise AdapterPermanentError(f"Facebook media publish failed: {parse_meta_error(payload)}")
            payload = response.json()

        external_post_id = str(payload.get("id") or "")
        if not external_post_id:
            raise AdapterPermanentError("Facebook media publish response missing post id")
        return {
            "external_post_id": external_post_id,
            "channel_type": self.channel_type,
            "platform": self.channel_type,
            "page_id": page.page_id,
            "page_name": page.page_name,
            "media": media,
        }
