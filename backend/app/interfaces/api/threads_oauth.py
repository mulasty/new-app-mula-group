from datetime import UTC, datetime, timedelta
from uuid import UUID

import httpx
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.application.services.social_account_service import upsert_social_account
from app.core.config import settings
from app.domain.models.channel import ChannelType
from app.integrations.oauth_state import create_oauth_state, verify_and_consume_oauth_state
from app.interfaces.api.social_oauth_utils import ensure_channel_for_platform

THREADS_AUTHORIZE_URL = "https://threads.net/oauth/authorize"
THREADS_TOKEN_URL = "https://graph.threads.net/oauth/access_token"
THREADS_LONG_LIVED_TOKEN_URL = "https://graph.threads.net/access_token"
THREADS_ME_URL = "https://graph.threads.net/v1.0/me"


def _require_threads_config() -> None:
    if not settings.threads_app_id or not settings.threads_app_secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Threads OAuth is not configured",
        )


def build_threads_oauth_authorization_url(*, company_id: UUID, project_id: UUID, user_id: UUID) -> str:
    _require_threads_config()
    state = create_oauth_state(
        provider=ChannelType.THREADS.value,
        company_id=company_id,
        project_id=project_id,
        user_id=user_id,
    )
    params = {
        "client_id": settings.threads_app_id,
        "redirect_uri": settings.threads_redirect_uri,
        "scope": settings.threads_oauth_scope,
        "response_type": "code",
        "state": state,
    }
    return str(httpx.URL(THREADS_AUTHORIZE_URL, params=params))


def decode_threads_state(state: str) -> dict:
    return verify_and_consume_oauth_state(state, provider=ChannelType.THREADS.value)


def exchange_threads_code_for_tokens(code: str) -> dict:
    _require_threads_config()
    data = {
        "client_id": settings.threads_app_id,
        "client_secret": settings.threads_app_secret,
        "grant_type": "authorization_code",
        "redirect_uri": settings.threads_redirect_uri,
        "code": code,
    }
    with httpx.Client(timeout=20.0) as client:
        response = client.post(THREADS_TOKEN_URL, data=data)
        if response.status_code >= 400:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Threads token exchange failed: {response.status_code}",
            )
        return response.json()


def exchange_threads_long_lived_token(short_lived_access_token: str) -> dict:
    _require_threads_config()
    params = {
        "grant_type": "th_exchange_token",
        "client_secret": settings.threads_app_secret,
        "access_token": short_lived_access_token,
    }
    with httpx.Client(timeout=20.0) as client:
        response = client.get(THREADS_LONG_LIVED_TOKEN_URL, params=params)
        if response.status_code >= 400:
            return {"access_token": short_lived_access_token, "expires_in": 3600}
        return response.json()


def fetch_threads_profile(access_token: str) -> dict:
    params = {"fields": "id,username", "access_token": access_token}
    with httpx.Client(timeout=20.0) as client:
        response = client.get(THREADS_ME_URL, params=params)
        if response.status_code >= 400:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Threads profile fetch failed: {response.status_code}",
            )
        data = response.json()
        if not data.get("id"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Threads profile id missing")
        return data


def store_threads_account_and_channel(
    db: Session,
    *,
    company_id: UUID,
    project_id: UUID,
    external_account_id: str,
    display_name: str | None,
    access_token: str,
    refresh_token: str | None,
    expires_in_seconds: int,
) -> None:
    now = datetime.now(UTC)
    expires_at = now + timedelta(seconds=max(1, int(expires_in_seconds)))
    upsert_social_account(
        db,
        company_id=company_id,
        platform=ChannelType.THREADS.value,
        external_account_id=external_account_id,
        display_name=display_name,
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=expires_at,
        metadata_json={"provider": "threads"},
    )
    ensure_channel_for_platform(
        db,
        company_id=company_id,
        project_id=project_id,
        channel_type=ChannelType.THREADS.value,
        channel_name=f"Threads @{display_name}" if display_name else "Threads",
    )
    db.commit()
