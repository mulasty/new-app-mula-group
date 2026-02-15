from datetime import UTC, datetime, timedelta
from uuid import UUID

import httpx
import jwt
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.services.social_account_service import upsert_social_account
from app.core.config import settings
from app.core.security import encrypt_secret
from app.domain.models.channel import Channel, ChannelType
from app.domain.models.linkedin_account import LinkedInAccount
from app.domain.models.project import Project

LINKEDIN_OAUTH_AUTHORIZE_URL = "https://www.linkedin.com/oauth/v2/authorization"
LINKEDIN_OAUTH_ACCESS_TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
LINKEDIN_USERINFO_URL = "https://api.linkedin.com/v2/userinfo"


def _require_linkedin_config() -> None:
    if not settings.linkedin_client_id or not settings.linkedin_client_secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="LinkedIn OAuth is not configured",
        )


def _create_state(*, company_id: UUID, project_id: UUID, user_id: UUID) -> str:
    expires_at = datetime.now(UTC) + timedelta(minutes=10)
    payload = {
        "type": "linkedin_oauth_state",
        "company_id": str(company_id),
        "project_id": str(project_id),
        "user_id": str(user_id),
        "exp": expires_at,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_state(state: str) -> dict:
    try:
        payload = jwt.decode(state, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OAuth state") from exc

    if payload.get("type") != "linkedin_oauth_state":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OAuth state type")
    return payload


def resolve_project_for_linkedin(db: Session, *, company_id: UUID, project_id: UUID | None) -> Project:
    if project_id is not None:
        project = db.execute(
            select(Project).where(Project.id == project_id, Project.company_id == company_id)
        ).scalar_one_or_none()
        if project is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
        return project

    project = db.execute(
        select(Project).where(Project.company_id == company_id).order_by(Project.created_at.asc())
    ).scalar_one_or_none()
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Create a project before connecting LinkedIn",
        )
    return project


def build_oauth_authorization_url(*, company_id: UUID, project_id: UUID, user_id: UUID) -> str:
    _require_linkedin_config()
    state = _create_state(company_id=company_id, project_id=project_id, user_id=user_id)
    params = {
        "response_type": "code",
        "client_id": settings.linkedin_client_id,
        "redirect_uri": settings.linkedin_redirect_uri,
        "scope": settings.linkedin_oauth_scope,
        "state": state,
    }
    return str(httpx.URL(LINKEDIN_OAUTH_AUTHORIZE_URL, params=params))


def exchange_code_for_tokens(code: str) -> dict:
    _require_linkedin_config()
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.linkedin_redirect_uri,
        "client_id": settings.linkedin_client_id,
        "client_secret": settings.linkedin_client_secret,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    with httpx.Client(timeout=20.0) as client:
        response = client.post(LINKEDIN_OAUTH_ACCESS_TOKEN_URL, data=data, headers=headers)
        if response.status_code >= 400:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"LinkedIn token exchange failed: {response.status_code}",
            )
        return response.json()


def fetch_linkedin_userinfo(access_token: str) -> dict:
    headers = {"Authorization": f"Bearer {access_token}"}
    with httpx.Client(timeout=20.0) as client:
        response = client.get(LINKEDIN_USERINFO_URL, headers=headers)
        if response.status_code >= 400:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"LinkedIn user profile fetch failed: {response.status_code}",
            )
        return response.json()


def store_linkedin_account_and_channel(
    db: Session,
    *,
    company_id: UUID,
    project_id: UUID,
    access_token: str,
    refresh_token: str,
    expires_in_seconds: int,
    linkedin_member_id: str,
    account_name: str | None = None,
) -> tuple[LinkedInAccount, Channel]:
    now = datetime.now(UTC)
    expires_at = now + timedelta(seconds=expires_in_seconds)

    account = db.execute(
        select(LinkedInAccount).where(LinkedInAccount.company_id == company_id)
    ).scalar_one_or_none()
    if account is None:
        account = LinkedInAccount(
            company_id=company_id,
            linkedin_member_id=linkedin_member_id,
            access_token=encrypt_secret(access_token),
            refresh_token=encrypt_secret(refresh_token or ""),
            expires_at=expires_at,
        )
        db.add(account)
    else:
        account.access_token = encrypt_secret(access_token)
        account.refresh_token = encrypt_secret(refresh_token or "")
        account.expires_at = expires_at
        db.add(account)

    channel = db.execute(
        select(Channel).where(
            Channel.company_id == company_id,
            Channel.project_id == project_id,
            Channel.type == ChannelType.LINKEDIN.value,
        )
    ).scalar_one_or_none()
    if channel is None:
        channel = Channel(
            company_id=company_id,
            project_id=project_id,
            type=ChannelType.LINKEDIN.value,
            name=(account_name or f"LinkedIn {linkedin_member_id[:8]}").strip(),
        )
        db.add(channel)
    else:
        channel.status = "active"
        if account_name:
            channel.name = account_name.strip()
        db.add(channel)

    upsert_social_account(
        db,
        company_id=company_id,
        platform=ChannelType.LINKEDIN.value,
        external_account_id=linkedin_member_id,
        display_name=account_name,
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=expires_at,
        metadata_json={"source": "linkedin_oauth"},
    )

    db.commit()
    db.refresh(account)
    db.refresh(channel)
    return account, channel
