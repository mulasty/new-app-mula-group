from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import decrypt_secret, encrypt_secret
from app.domain.models.facebook_account import FacebookAccount
from app.domain.models.facebook_page import FacebookPage
from app.domain.models.instagram_account import InstagramAccount


def _require_meta_config() -> None:
    if not settings.meta_app_id or not settings.meta_app_secret:
        raise ValueError("Meta client configuration is missing")


async def ensure_valid_facebook_user_token(db: Session, company_id: UUID) -> str:
    account = db.execute(
        select(FacebookAccount)
        .where(FacebookAccount.company_id == company_id)
        .order_by(FacebookAccount.created_at.asc())
    ).scalar_one_or_none()
    if account is None:
        raise ValueError("Meta account not connected for tenant")

    now = datetime.now(UTC)
    if account.expires_at > now + timedelta(minutes=10):
        return decrypt_secret(account.access_token)

    _require_meta_config()
    existing_access_token = decrypt_secret(account.access_token)
    params = {
        "grant_type": "fb_exchange_token",
        "client_id": settings.meta_app_id,
        "client_secret": settings.meta_app_secret,
        "fb_exchange_token": existing_access_token,
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(f"{settings.meta_graph_api_base_url}/oauth/access_token", params=params)
        if response.status_code >= 400:
            raise ValueError(f"Meta token refresh failed: {response.status_code} {response.text}")
        payload = response.json()

    refreshed_token = str(payload.get("access_token") or "")
    if not refreshed_token:
        raise ValueError("Meta token refresh response missing access_token")

    expires_in = int(payload.get("expires_in", 5184000))
    account.access_token = encrypt_secret(refreshed_token)
    account.expires_at = now + timedelta(seconds=expires_in)
    db.add(account)
    db.commit()
    return refreshed_token


def pick_facebook_page(db: Session, *, company_id: UUID, preferred_channel_name: str | None = None) -> FacebookPage:
    pages = db.execute(
        select(FacebookPage).where(FacebookPage.company_id == company_id).order_by(FacebookPage.created_at.asc())
    ).scalars().all()
    if not pages:
        raise ValueError("No connected Facebook page found for tenant")

    if preferred_channel_name:
        normalized = preferred_channel_name.lower()
        for page in pages:
            if page.page_name.lower() in normalized or normalized.endswith(page.page_name.lower()):
                return page

    return pages[0]


def pick_instagram_account(
    db: Session,
    *,
    company_id: UUID,
    preferred_channel_name: str | None = None,
) -> InstagramAccount:
    rows = db.execute(
        select(InstagramAccount)
        .where(InstagramAccount.company_id == company_id)
        .order_by(InstagramAccount.created_at.asc())
    ).scalars().all()
    if not rows:
        raise ValueError("No connected Instagram business account found for tenant")

    if preferred_channel_name:
        normalized = preferred_channel_name.lower()
        for account in rows:
            username = (account.username or "").lower()
            if username and username in normalized:
                return account

    return rows[0]


def resolve_instagram_page_token(
    db: Session,
    *,
    company_id: UUID,
    instagram_account: InstagramAccount,
) -> str:
    query = select(FacebookPage).where(FacebookPage.company_id == company_id)
    if instagram_account.linked_page_id:
        query = query.where(FacebookPage.page_id == instagram_account.linked_page_id)

    page = db.execute(query.order_by(FacebookPage.created_at.asc())).scalars().first()
    if page is None:
        raise ValueError("No linked Facebook page token found for Instagram account")
    return decrypt_secret(page.access_token)


def parse_meta_error(payload: dict[str, Any]) -> str:
    error_obj = payload.get("error") if isinstance(payload, dict) else None
    if not isinstance(error_obj, dict):
        return "Meta API error"
    message = str(error_obj.get("message") or "Meta API error")
    code = error_obj.get("code")
    subcode = error_obj.get("error_subcode")
    parts = [message]
    if code is not None:
        parts.append(f"code={code}")
    if subcode is not None:
        parts.append(f"subcode={subcode}")
    return " | ".join(parts)
