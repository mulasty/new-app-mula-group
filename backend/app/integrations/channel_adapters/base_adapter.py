from abc import ABC, abstractmethod
import re
from typing import ClassVar

from app.application.services.connector_credentials_service import is_credential_revoked
from app.domain.models.channel import Channel
from app.domain.models.post import Post


class AdapterResolutionError(RuntimeError):
    pass


class AdapterError(RuntimeError):
    retryable: bool = True
    error_code: str = "adapter_error"


class AdapterRetryableError(AdapterError):
    retryable = True
    error_code = "adapter_retryable_error"


class AdapterPermanentError(AdapterError):
    retryable = False
    error_code = "adapter_permanent_error"


class AdapterAuthError(AdapterPermanentError):
    error_code = "adapter_auth_error"


class BaseChannelAdapter(ABC):
    channel_type: ClassVar[str] = ""
    is_fallback: ClassVar[bool] = False
    _MEDIA_URL_PATTERN = re.compile(r"https?://[^\s]+", re.IGNORECASE)

    @classmethod
    def get_capabilities(cls) -> dict:
        return {
            "text": True,
            "image": False,
            "video": False,
            "reels": False,
            "shorts": False,
            "max_length": 3000,
        }

    @abstractmethod
    async def validate_credentials(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def publish_text(self, *, post: Post, channel: Channel) -> dict:
        raise NotImplementedError

    @abstractmethod
    async def publish_media(self, *, post: Post, channel: Channel) -> dict:
        raise NotImplementedError

    @abstractmethod
    async def refresh_credentials(self) -> None:
        raise NotImplementedError

    def _extract_media_reference(self, post: Post) -> str | None:
        match = self._MEDIA_URL_PATTERN.search(post.content or "")
        return match.group(0) if match else None

    async def publish_post(self, *, post: Post, channel: Channel) -> dict:
        """
        Universal publish flow used by the worker.
        1) Validate credentials
        2) Route to text/media publish method based on post payload
        3) Retry credential validation once after refresh
        """
        capabilities = self.get_capabilities()
        media_reference = self._extract_media_reference(post)
        can_publish_media = bool(
            capabilities.get("image") or capabilities.get("video") or capabilities.get("reels") or capabilities.get("shorts")
        )
        db = getattr(self, "db", None)
        if db is not None and is_credential_revoked(db, tenant_id=post.company_id, connector_type=channel.type):
            raise AdapterAuthError(f"Connector credential revoked for {channel.type}")

        try:
            await self.validate_credentials()
        except AdapterAuthError:
            try:
                await self.refresh_credentials()
            except AdapterAuthError:
                await self.refresh_credentials()
            await self.validate_credentials()

        if media_reference and can_publish_media:
            return await self.publish_media(post=post, channel=channel)
        return await self.publish_text(post=post, channel=channel)
