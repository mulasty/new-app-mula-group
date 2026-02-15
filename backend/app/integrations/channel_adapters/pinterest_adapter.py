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

PINTEREST_TOKEN_URL = "https://api.pinterest.com/v5/oauth/token"
PINTEREST_USER_ACCOUNT_URL = "https://api.pinterest.com/v5/user_account"
PINTEREST_BOARDS_URL = "https://api.pinterest.com/v5/boards"
PINTEREST_CREATE_PIN_URL = "https://api.pinterest.com/v5/pins"


class PinterestAdapter(BaseChannelAdapter):
    channel_type = ChannelType.PINTEREST.value

    def __init__(self, db: Session) -> None:
        self.db = db
        self._current_post: Post | None = None
        self._active_access_token: str | None = None

    @classmethod
    def get_capabilities(cls) -> dict:
        return {
            "text": False,
            "image": True,
            "video": False,
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
            raise AdapterAuthError("Pinterest adapter context missing post")
        account = load_platform_account(self.db, company_id=self._current_post.company_id, platform=self.channel_type)
        if account is None:
            raise AdapterAuthError("Pinterest account not connected for tenant")
        if is_token_expiring(account, within_seconds=90):
            self._active_access_token = await self._refresh_access_token()
        else:
            self._active_access_token = decrypted_access_token(account)
        if not self._active_access_token:
            raise AdapterAuthError("Pinterest access token unavailable")

        headers = {"Authorization": f"Bearer {self._active_access_token}"}
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(PINTEREST_USER_ACCOUNT_URL, headers=headers)
            if response.status_code in {401, 403}:
                raise AdapterAuthError("Pinterest access token invalid or unauthorized")
            if response.status_code >= 500:
                raise AdapterRetryableError("Pinterest API unavailable during credential validation")
            if response.status_code >= 400:
                raise AdapterPermanentError(
                    f"Pinterest credential validation failed: {response.status_code}"
                )

    async def refresh_credentials(self) -> None:
        self._active_access_token = await self._refresh_access_token()

    async def publish_text(self, *, post: Post, channel: Channel) -> dict:
        raise AdapterPermanentError("Pinterest publish requires media URL and board context")

    async def publish_media(self, *, post: Post, channel: Channel) -> dict:
        access_token = self._active_access_token
        if not access_token:
            await self.validate_credentials()
            access_token = self._active_access_token
        if not access_token:
            raise AdapterAuthError("Pinterest access token unavailable")

        account = load_platform_account(self.db, company_id=post.company_id, platform=self.channel_type)
        if account is None:
            raise AdapterAuthError("Pinterest account not connected for tenant")

        media_reference = self._extract_media_reference(post)
        if not media_reference:
            raise AdapterPermanentError("Pinterest publish requires an image URL in post content")
        media = await upload_media(self.channel_type, media_reference)

        metadata_json = account.metadata_json or {}
        board_id = metadata_json.get("default_board_id") if isinstance(metadata_json, dict) else None
        board_id = str(board_id) if board_id else await self._fetch_default_board_id(access_token)
        if not board_id:
            raise AdapterPermanentError("Pinterest board not found for connected account")

        payload = {
            "board_id": board_id,
            "title": post.title[:100],
            "description": post.content[:500],
            "media_source": {"source_type": "image_url", "url": media["source_url"]},
        }
        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=25.0) as client:
            response = await client.post(PINTEREST_CREATE_PIN_URL, headers=headers, json=payload)
            if response.status_code in {401, 403}:
                raise AdapterAuthError("Pinterest publish unauthorized")
            if response.status_code == 429 or response.status_code >= 500:
                raise AdapterRetryableError(f"Pinterest publish temporary failure: {response.status_code}")
            if response.status_code >= 400:
                raise AdapterPermanentError(f"Pinterest publish failed: {response.status_code} {response.text}")
            data = response.json()

        external_post_id = str(data.get("id") or "")
        if not external_post_id:
            raise AdapterPermanentError("Pinterest publish response missing pin id")
        return {
            "external_post_id": external_post_id,
            "channel_type": self.channel_type,
            "platform": self.channel_type,
            "board_id": board_id,
            "media": media,
        }

    async def _fetch_default_board_id(self, access_token: str) -> str | None:
        headers = {"Authorization": f"Bearer {access_token}"}
        params = {"page_size": 1}
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(PINTEREST_BOARDS_URL, headers=headers, params=params)
            if response.status_code >= 400:
                return None
            payload = response.json()
            items = payload.get("items") or []
            if not items:
                return None
            board = items[0] or {}
            board_id = board.get("id")
            return str(board_id) if board_id else None

    async def _refresh_access_token(self) -> str:
        if self._current_post is None:
            raise AdapterAuthError("Pinterest adapter context missing post")
        if not settings.pinterest_client_id or not settings.pinterest_client_secret:
            raise AdapterAuthError("Pinterest OAuth client configuration missing")

        account = load_platform_account(self.db, company_id=self._current_post.company_id, platform=self.channel_type)
        if account is None:
            raise AdapterAuthError("Pinterest account not connected for tenant")
        refresh_token = decrypted_refresh_token(account)
        if not refresh_token:
            raise AdapterAuthError("Pinterest refresh token not available")

        data = {"grant_type": "refresh_token", "refresh_token": refresh_token}
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                PINTEREST_TOKEN_URL,
                data=data,
                headers=headers,
                auth=(settings.pinterest_client_id, settings.pinterest_client_secret),
            )
            if response.status_code in {401, 403}:
                raise AdapterAuthError("Pinterest refresh token unauthorized")
            if response.status_code >= 500:
                raise AdapterRetryableError("Pinterest token refresh temporary failure")
            if response.status_code >= 400:
                raise AdapterAuthError(
                    f"Pinterest token refresh failed: {response.status_code} {response.text}"
                )
            payload = response.json()

        access_token = str(payload.get("access_token") or "")
        if not access_token:
            raise AdapterAuthError("Pinterest refresh response missing access token")
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
