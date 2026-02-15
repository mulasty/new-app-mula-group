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

TIKTOK_AUTHORIZE_URL = "https://www.tiktok.com/v2/auth/authorize/"
TIKTOK_TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
TIKTOK_USERINFO_URL = "https://open.tiktokapis.com/v2/user/info/"
TIKTOK_CREATOR_INFO_URL = "https://open.tiktokapis.com/v2/post/publish/creator_info/query/"


def _require_tiktok_config() -> None:
    if not settings.tiktok_client_key or not settings.tiktok_client_secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="TikTok OAuth is not configured",
        )


def _build_code_challenge(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")


def build_tiktok_oauth_authorization_url(*, company_id: UUID, project_id: UUID, user_id: UUID) -> str:
    _require_tiktok_config()
    code_verifier = secrets.token_urlsafe(48)
    code_challenge = _build_code_challenge(code_verifier)
    state = create_oauth_state(
        provider=ChannelType.TIKTOK.value,
        company_id=company_id,
        project_id=project_id,
        user_id=user_id,
        extra={"code_verifier": code_verifier},
    )
    params = {
        "client_key": settings.tiktok_client_key,
        "response_type": "code",
        "redirect_uri": settings.tiktok_redirect_uri,
        "scope": settings.tiktok_oauth_scope,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return str(httpx.URL(TIKTOK_AUTHORIZE_URL, params=params))


def decode_tiktok_state(state: str) -> dict:
    payload = verify_and_consume_oauth_state(state, provider=ChannelType.TIKTOK.value)
    extra = payload.get("extra") or {}
    code_verifier = extra.get("code_verifier")
    if not isinstance(code_verifier, str) or not code_verifier:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing TikTok OAuth code verifier")
    payload["code_verifier"] = code_verifier
    return payload


def exchange_tiktok_code_for_tokens(*, code: str, code_verifier: str) -> dict:
    _require_tiktok_config()
    data = {
        "client_key": settings.tiktok_client_key,
        "client_secret": settings.tiktok_client_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": settings.tiktok_redirect_uri,
        "code_verifier": code_verifier,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    with httpx.Client(timeout=20.0) as client:
        response = client.post(TIKTOK_TOKEN_URL, data=data, headers=headers)
        if response.status_code >= 400:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"TikTok token exchange failed: {response.status_code}",
            )
        payload = response.json()
        error = payload.get("error")
        if error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"TikTok token exchange failed: {error}",
            )
        return payload


def fetch_tiktok_userinfo(access_token: str) -> dict:
    headers = {"Authorization": f"Bearer {access_token}"}
    params = {"fields": "open_id,display_name,avatar_url"}
    with httpx.Client(timeout=20.0) as client:
        response = client.get(TIKTOK_USERINFO_URL, headers=headers, params=params)
        if response.status_code >= 400:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"TikTok profile fetch failed: {response.status_code}",
            )
        payload = response.json()
        data = payload.get("data") or {}
        user = data.get("user") or {}
        if not user.get("open_id"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="TikTok user id missing")
        return user


def fetch_tiktok_creator_info(access_token: str) -> dict:
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=UTF-8",
    }
    with httpx.Client(timeout=20.0) as client:
        response = client.post(TIKTOK_CREATOR_INFO_URL, headers=headers, json={})
        if response.status_code >= 400:
            return {}
        payload = response.json()
        if payload.get("error", {}).get("code") not in {None, "ok"}:
            return {}
        return payload.get("data") or {}


def store_tiktok_account_and_channel(
    db: Session,
    *,
    company_id: UUID,
    project_id: UUID,
    access_token: str,
    refresh_token: str,
    expires_in_seconds: int,
    external_account_id: str,
    display_name: str | None,
    creator_info: dict | None = None,
) -> None:
    now = datetime.now(UTC)
    expires_at = now + timedelta(seconds=max(1, int(expires_in_seconds)))
    metadata_json = {
        "provider": "tiktok",
        "creator_info": creator_info or {},
    }
    upsert_social_account(
        db,
        company_id=company_id,
        platform=ChannelType.TIKTOK.value,
        external_account_id=external_account_id,
        display_name=display_name,
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=expires_at,
        metadata_json=metadata_json,
    )
    ensure_channel_for_platform(
        db,
        company_id=company_id,
        project_id=project_id,
        channel_type=ChannelType.TIKTOK.value,
        channel_name=(display_name or "TikTok").strip(),
    )
    db.commit()
