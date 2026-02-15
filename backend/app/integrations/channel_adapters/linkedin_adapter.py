from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import decrypt_secret, encrypt_secret
from app.domain.models.channel import Channel
from app.domain.models.linkedin_account import LinkedInAccount
from app.domain.models.post import Post
from app.integrations.channel_adapters.base_adapter import (
    AdapterAuthError,
    AdapterPermanentError,
    AdapterRetryableError,
    BaseChannelAdapter,
)

LINKEDIN_REFRESH_URL = "https://www.linkedin.com/oauth/v2/accessToken"
LINKEDIN_UGC_POSTS_URL = "https://api.linkedin.com/v2/ugcPosts"


class LinkedInAdapter(BaseChannelAdapter):
    channel_type = "linkedin"

    def __init__(self, db: Session) -> None:
        self.db = db
        self._current_post: Post | None = None
        self._active_access_token: str | None = None
        self._active_account: LinkedInAccount | None = None

    @classmethod
    def get_capabilities(cls) -> dict:
        return {
            "text": True,
            "image": True,
            "video": False,
            "reels": False,
            "shorts": False,
            "max_length": 3000,
        }

    async def validate_credentials(self) -> None:
        if self._active_account is None and self._current_post is not None:
            self._active_account = self.db.execute(
                select(LinkedInAccount).where(LinkedInAccount.company_id == self._current_post.company_id)
            ).scalar_one_or_none()
        if self._active_account is None:
            raise AdapterAuthError("LinkedIn account context is not initialized")
        self._active_access_token = await self._ensure_valid_access_token(self._active_account)

    async def refresh_credentials(self) -> None:
        if self._active_account is None and self._current_post is not None:
            self._active_account = self.db.execute(
                select(LinkedInAccount).where(LinkedInAccount.company_id == self._current_post.company_id)
            ).scalar_one_or_none()
        if self._active_account is None:
            raise AdapterAuthError("LinkedIn account context is not initialized")
        self._active_access_token = await self._refresh_access_token(self._active_account)

    async def publish_post(self, *, post: Post, channel: Channel) -> dict:
        self._current_post = post
        self._active_access_token = None
        self._active_account = None
        return await super().publish_post(post=post, channel=channel)

    async def publish_text(self, *, post: Post, channel: Channel) -> dict:
        account = self.db.execute(
            select(LinkedInAccount).where(LinkedInAccount.company_id == post.company_id)
        ).scalar_one_or_none()
        if account is None:
            raise AdapterAuthError("LinkedIn account not connected for tenant")
        self._active_account = account
        access_token = self._active_access_token or await self._ensure_valid_access_token(account)

        return await self._publish_ugc_post(
            access_token=access_token,
            author_member_id=account.linkedin_member_id,
            text=f"{post.title}\n\n{post.content}",
            share_media_category="NONE",
            media_payload=None,
        )

    async def publish_media(self, *, post: Post, channel: Channel) -> dict:
        # In phase 5.1 we keep LinkedIn publishing text-only for stability.
        return await self.publish_text(post=post, channel=channel)

    async def _publish_ugc_post(
        self,
        *,
        access_token: str,
        author_member_id: str,
        text: str,
        share_media_category: str,
        media_payload: list[dict] | None,
    ) -> dict:
        author_urn = f"urn:li:person:{author_member_id}"
        share_content: dict = {
            "shareCommentary": {"text": text},
            "shareMediaCategory": share_media_category,
        }
        if media_payload:
            share_content["media"] = media_payload
        payload = {
            "author": author_urn,
            "lifecycleState": "PUBLISHED",
            "specificContent": {"com.linkedin.ugc.ShareContent": share_content},
            "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
        }
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0",
        }

        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(LINKEDIN_UGC_POSTS_URL, json=payload, headers=headers)
            if response.status_code >= 400:
                if response.status_code in {401, 403}:
                    raise AdapterAuthError(
                        f"LinkedIn publish unauthorized: {response.status_code} {response.text}"
                    )
                if response.status_code == 429 or response.status_code >= 500:
                    raise AdapterRetryableError(
                        f"LinkedIn publish temporary failure: {response.status_code} {response.text}"
                    )
                raise AdapterPermanentError(
                    f"LinkedIn publish failed: {response.status_code} {response.text}"
                )

            external_post_id = response.headers.get("x-restli-id")
            if not external_post_id:
                response_json = response.json() if response.content else {}
                external_post_id = str(response_json.get("id") or "")
            if not external_post_id:
                raise AdapterPermanentError("LinkedIn publish response missing post id")

        return {
            "external_post_id": external_post_id,
            "channel_type": self.channel_type,
            "platform": self.channel_type,
        }

    async def _ensure_valid_access_token(self, account: LinkedInAccount) -> str:
        now = datetime.now(UTC)
        if account.expires_at > now + timedelta(seconds=60):
            return decrypt_secret(account.access_token)
        return await self._refresh_access_token(account)

    async def _refresh_access_token(self, account: LinkedInAccount) -> str:
        now = datetime.now(UTC)

        refresh_token = decrypt_secret(account.refresh_token)
        if not refresh_token:
            raise AdapterAuthError("LinkedIn refresh token not available")
        if not settings.linkedin_client_id or not settings.linkedin_client_secret:
            raise AdapterAuthError("LinkedIn client configuration is missing")

        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": settings.linkedin_client_id,
            "client_secret": settings.linkedin_client_secret,
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(LINKEDIN_REFRESH_URL, data=data, headers=headers)
            if response.status_code >= 400:
                if response.status_code in {401, 403}:
                    raise AdapterAuthError(
                        f"LinkedIn token refresh denied: {response.status_code} {response.text}"
                    )
                if response.status_code == 429 or response.status_code >= 500:
                    raise AdapterRetryableError(
                        f"LinkedIn token refresh temporary failure: {response.status_code} {response.text}"
                    )
                raise AdapterPermanentError(
                    f"LinkedIn token refresh failed: {response.status_code} {response.text}"
                )
            token_payload = response.json()

        access_token = token_payload.get("access_token")
        if not access_token:
            raise AdapterPermanentError("LinkedIn token refresh response missing access_token")

        refresh_token_next = token_payload.get("refresh_token") or refresh_token
        expires_in = int(token_payload.get("expires_in", 3600))
        account.access_token = encrypt_secret(access_token)
        account.refresh_token = encrypt_secret(refresh_token_next)
        account.expires_at = now + timedelta(seconds=expires_in)
        self.db.add(account)
        self.db.flush()
        return access_token
