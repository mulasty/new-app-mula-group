import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
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
    pick_instagram_account,
    resolve_instagram_page_token,
)
from app.integrations.media_upload_service import upload_media


class InstagramAdapter(BaseChannelAdapter):
    channel_type = "instagram"

    def __init__(self, db: Session) -> None:
        self.db = db
        self._current_post: Post | None = None

    @classmethod
    def get_capabilities(cls) -> dict:
        return {
            "text": True,
            "image": True,
            "video": True,
            "reels": True,
            "shorts": False,
            "max_length": 2200,
        }

    async def publish_post(self, *, post: Post, channel: Channel) -> dict:
        self._current_post = post
        return await super().publish_post(post=post, channel=channel)

    async def validate_credentials(self) -> None:
        if self._current_post is None:
            raise AdapterAuthError("Instagram adapter context missing post")
        try:
            await ensure_valid_facebook_user_token(self.db, self._current_post.company_id)
        except ValueError as exc:
            raise AdapterAuthError(str(exc)) from exc

    async def refresh_credentials(self) -> None:
        if self._current_post is None:
            raise AdapterAuthError("Instagram adapter context missing post")
        try:
            await ensure_valid_facebook_user_token(self.db, self._current_post.company_id)
        except ValueError as exc:
            raise AdapterAuthError(str(exc)) from exc

    async def publish_text(self, *, post: Post, channel: Channel) -> dict:
        raise AdapterPermanentError("Instagram publish requires media URL in post content")

    async def publish_media(self, *, post: Post, channel: Channel) -> dict:
        instagram_account = pick_instagram_account(
            self.db,
            company_id=post.company_id,
            preferred_channel_name=channel.name,
        )
        page_access_token = resolve_instagram_page_token(
            self.db,
            company_id=post.company_id,
            instagram_account=instagram_account,
        )
        caption = f"{post.title}\n\n{post.content}".strip()
        media_reference = self._extract_media_reference(post)
        if not media_reference:
            raise AdapterPermanentError("Instagram publish requires an image URL in post content")
        media = await upload_media(self.channel_type, media_reference)

        container_payload = {
            "caption": caption,
            "image_url": media["source_url"],
            "access_token": page_access_token,
        }

        async with httpx.AsyncClient(timeout=20.0) as client:
            container_response = await client.post(
                f"{settings.meta_graph_api_base_url}/{instagram_account.instagram_account_id}/media",
                data=container_payload,
            )
            if container_response.status_code >= 400:
                payload = (
                    container_response.json()
                    if container_response.headers.get("content-type", "").startswith("application/json")
                    else {}
                )
                if container_response.status_code in {401, 403}:
                    raise AdapterAuthError(f"Instagram container unauthorized: {parse_meta_error(payload)}")
                if container_response.status_code == 429 or container_response.status_code >= 500:
                    raise AdapterRetryableError(
                        f"Instagram container temporary failure: {parse_meta_error(payload)}"
                    )
                raise AdapterPermanentError(f"Instagram container creation failed: {parse_meta_error(payload)}")
            container_id = str(container_response.json().get("id") or "")
            if not container_id:
                raise AdapterPermanentError("Instagram container response missing id")

            publish_response = await client.post(
                f"{settings.meta_graph_api_base_url}/{instagram_account.instagram_account_id}/media_publish",
                data={"creation_id": container_id, "access_token": page_access_token},
            )
            if publish_response.status_code >= 400:
                payload = (
                    publish_response.json()
                    if publish_response.headers.get("content-type", "").startswith("application/json")
                    else {}
                )
                if publish_response.status_code in {401, 403}:
                    raise AdapterAuthError(f"Instagram publish unauthorized: {parse_meta_error(payload)}")
                if publish_response.status_code == 429 or publish_response.status_code >= 500:
                    raise AdapterRetryableError(f"Instagram publish temporary failure: {parse_meta_error(payload)}")
                raise AdapterPermanentError(f"Instagram publish failed: {parse_meta_error(payload)}")
            payload = publish_response.json()

        external_post_id = str(payload.get("id") or "")
        if not external_post_id:
            raise AdapterPermanentError("Instagram publish response missing post id")

        return {
            "external_post_id": external_post_id,
            "channel_type": self.channel_type,
            "platform": self.channel_type,
            "instagram_account_id": instagram_account.instagram_account_id,
            "username": instagram_account.username,
            "media": media,
        }
