import base64
import hashlib
import secrets
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

X_AUTHORIZE_URL = "https://x.com/i/oauth2/authorize"
X_TOKEN_URL = "https://api.x.com/2/oauth2/token"
X_ME_URL = "https://api.x.com/2/users/me"


def _require_x_config() -> None:
    if not settings.x_client_id or not settings.x_client_secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="X OAuth is not configured",
        )


def _build_code_challenge(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")


def build_x_oauth_authorization_url(*, company_id: UUID, project_id: UUID, user_id: UUID) -> str:
    _require_x_config()
    code_verifier = secrets.token_urlsafe(48)
    code_challenge = _build_code_challenge(code_verifier)
    state = create_oauth_state(
        provider=ChannelType.X.value,
        company_id=company_id,
        project_id=project_id,
        user_id=user_id,
        extra={"code_verifier": code_verifier},
    )
    params = {
        "response_type": "code",
        "client_id": settings.x_client_id,
        "redirect_uri": settings.x_redirect_uri,
        "scope": settings.x_oauth_scope,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return str(httpx.URL(X_AUTHORIZE_URL, params=params))


def decode_x_state(state: str) -> dict:
    payload = verify_and_consume_oauth_state(state, provider=ChannelType.X.value)
    extra = payload.get("extra") or {}
    code_verifier = extra.get("code_verifier")
    if not isinstance(code_verifier, str) or not code_verifier:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing X OAuth code verifier")
    payload["code_verifier"] = code_verifier
    return payload


def exchange_x_code_for_tokens(*, code: str, code_verifier: str) -> dict:
    _require_x_config()
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.x_redirect_uri,
        "code_verifier": code_verifier,
        "client_id": settings.x_client_id,
    }
    with httpx.Client(timeout=20.0) as client:
        response = client.post(
            X_TOKEN_URL,
            data=data,
            auth=(settings.x_client_id, settings.x_client_secret),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if response.status_code >= 400:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"X token exchange failed: {response.status_code}",
            )
        return response.json()


def fetch_x_profile(access_token: str) -> dict:
    headers = {"Authorization": f"Bearer {access_token}"}
    with httpx.Client(timeout=20.0) as client:
        response = client.get(X_ME_URL, headers=headers)
        if response.status_code >= 400:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"X profile fetch failed: {response.status_code}",
            )
        payload = response.json()
        data = payload.get("data") or {}
        if not data.get("id"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="X profile id missing")
        return data


def store_x_account_and_channel(
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
        platform=ChannelType.X.value,
        external_account_id=external_account_id,
        display_name=display_name,
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=expires_at,
        metadata_json={"provider": "x"},
    )
    ensure_channel_for_platform(
        db,
        company_id=company_id,
        project_id=project_id,
        channel_type=ChannelType.X.value,
        channel_name=f"X @{display_name}" if display_name else "X",
    )
    db.commit()
