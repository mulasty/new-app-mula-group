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

PINTEREST_AUTHORIZE_URL = "https://www.pinterest.com/oauth/"
PINTEREST_TOKEN_URL = "https://api.pinterest.com/v5/oauth/token"
PINTEREST_USER_ACCOUNT_URL = "https://api.pinterest.com/v5/user_account"
PINTEREST_BOARDS_URL = "https://api.pinterest.com/v5/boards"


def _require_pinterest_config() -> None:
    if not settings.pinterest_client_id or not settings.pinterest_client_secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Pinterest OAuth is not configured",
        )


def build_pinterest_oauth_authorization_url(*, company_id: UUID, project_id: UUID, user_id: UUID) -> str:
    _require_pinterest_config()
    state = create_oauth_state(
        provider=ChannelType.PINTEREST.value,
        company_id=company_id,
        project_id=project_id,
        user_id=user_id,
    )
    params = {
        "response_type": "code",
        "client_id": settings.pinterest_client_id,
        "redirect_uri": settings.pinterest_redirect_uri,
        "scope": settings.pinterest_oauth_scope,
        "state": state,
    }
    return str(httpx.URL(PINTEREST_AUTHORIZE_URL, params=params))


def decode_pinterest_state(state: str) -> dict:
    return verify_and_consume_oauth_state(state, provider=ChannelType.PINTEREST.value)


def exchange_pinterest_code_for_tokens(code: str) -> dict:
    _require_pinterest_config()
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.pinterest_redirect_uri,
    }
    with httpx.Client(timeout=20.0) as client:
        response = client.post(
            PINTEREST_TOKEN_URL,
            data=data,
            auth=(settings.pinterest_client_id, settings.pinterest_client_secret),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if response.status_code >= 400:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Pinterest token exchange failed: {response.status_code}",
            )
        return response.json()


def fetch_pinterest_profile(access_token: str) -> dict:
    headers = {"Authorization": f"Bearer {access_token}"}
    with httpx.Client(timeout=20.0) as client:
        response = client.get(PINTEREST_USER_ACCOUNT_URL, headers=headers)
        if response.status_code >= 400:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Pinterest profile fetch failed: {response.status_code}",
            )
        payload = response.json()
        if not payload.get("username"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Pinterest profile username missing")
        return payload


def fetch_default_pinterest_board(access_token: str) -> str | None:
    headers = {"Authorization": f"Bearer {access_token}"}
    params = {"page_size": 1}
    with httpx.Client(timeout=20.0) as client:
        response = client.get(PINTEREST_BOARDS_URL, headers=headers, params=params)
        if response.status_code >= 400:
            return None
        payload = response.json()
        items = payload.get("items") or []
        if not items:
            return None
        board = items[0] or {}
        board_id = board.get("id")
        return str(board_id) if board_id else None


def store_pinterest_account_and_channel(
    db: Session,
    *,
    company_id: UUID,
    project_id: UUID,
    external_account_id: str,
    display_name: str | None,
    access_token: str,
    refresh_token: str | None,
    expires_in_seconds: int,
    default_board_id: str | None = None,
) -> None:
    now = datetime.now(UTC)
    expires_at = now + timedelta(seconds=max(1, int(expires_in_seconds)))
    upsert_social_account(
        db,
        company_id=company_id,
        platform=ChannelType.PINTEREST.value,
        external_account_id=external_account_id,
        display_name=display_name,
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=expires_at,
        metadata_json={"provider": "pinterest", "default_board_id": default_board_id},
    )
    ensure_channel_for_platform(
        db,
        company_id=company_id,
        project_id=project_id,
        channel_type=ChannelType.PINTEREST.value,
        channel_name=f"Pinterest @{display_name}" if display_name else "Pinterest",
    )
    db.commit()
