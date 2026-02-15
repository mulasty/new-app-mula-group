from urllib.parse import quote_plus
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models.channel import Channel, ChannelType
from app.domain.models.project import Project
from app.domain.models.user import User, UserRole
from app.interfaces.api.deps import get_current_user, require_roles, require_tenant_id
from app.interfaces.api.linkedin_oauth import (
    build_oauth_authorization_url,
    decode_state,
    exchange_code_for_tokens,
    fetch_linkedin_userinfo,
    resolve_project_for_linkedin,
    store_linkedin_account_and_channel,
)
from app.infrastructure.db.session import get_db

router = APIRouter(prefix="/channels", tags=["channels"])


class ChannelCreateRequest(BaseModel):
    project_id: UUID
    type: str = Field(default=ChannelType.WEBSITE.value)
    name: str | None = Field(default=None, min_length=1, max_length=255)


class ChannelStatusUpdateRequest(BaseModel):
    status: str = Field(pattern="^(active|disabled)$")


def _serialize_channel(channel: Channel) -> dict:
    return {
        "id": str(channel.id),
        "company_id": str(channel.company_id),
        "project_id": str(channel.project_id),
        "type": channel.type,
        "name": channel.name,
        "status": channel.status,
        "created_at": channel.created_at.isoformat(),
        "updated_at": channel.updated_at.isoformat(),
    }


@router.post("", status_code=status.HTTP_201_CREATED)
def create_channel(
    payload: ChannelCreateRequest,
    response: Response,
    db: Session = Depends(get_db),
    tenant_id: UUID = Depends(require_tenant_id),
    current_user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN)),
) -> dict:
    if payload.type != ChannelType.WEBSITE.value:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only website channel is supported")

    project = db.execute(
        select(Project).where(Project.id == payload.project_id, Project.company_id == tenant_id)
    ).scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    existing = db.execute(
        select(Channel).where(
            Channel.company_id == tenant_id,
            Channel.project_id == payload.project_id,
            Channel.type == ChannelType.WEBSITE.value,
        )
    ).scalar_one_or_none()

    if existing is not None:
        response.status_code = status.HTTP_200_OK
        return _serialize_channel(existing)

    channel = Channel(
        company_id=tenant_id,
        project_id=payload.project_id,
        type=ChannelType.WEBSITE.value,
        name=(payload.name or "Website").strip(),
    )
    db.add(channel)
    db.commit()
    db.refresh(channel)
    return _serialize_channel(channel)


@router.get("", status_code=status.HTTP_200_OK)
def list_channels(
    project_id: UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    tenant_id: UUID = Depends(require_tenant_id),
    current_user: User = Depends(get_current_user),
) -> dict:
    query = select(Channel).where(Channel.company_id == tenant_id)
    if project_id is not None:
        query = query.where(Channel.project_id == project_id)

    rows = db.execute(query.order_by(Channel.created_at.desc())).scalars().all()
    return {"items": [_serialize_channel(row) for row in rows]}


@router.patch("/{channel_id}/status", status_code=status.HTTP_200_OK)
def update_channel_status(
    channel_id: UUID,
    payload: ChannelStatusUpdateRequest,
    db: Session = Depends(get_db),
    tenant_id: UUID = Depends(require_tenant_id),
    current_user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN)),
) -> dict:
    channel = db.execute(
        select(Channel).where(Channel.id == channel_id, Channel.company_id == tenant_id)
    ).scalar_one_or_none()
    if channel is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel not found")

    channel.status = payload.status
    db.add(channel)
    db.commit()
    db.refresh(channel)
    return _serialize_channel(channel)


@router.get("/linkedin/oauth/start", status_code=status.HTTP_200_OK)
def linkedin_oauth_start(
    project_id: UUID | None = Query(default=None),
    redirect: bool = Query(default=True),
    db: Session = Depends(get_db),
    tenant_id: UUID = Depends(require_tenant_id),
    current_user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN)),
):
    project = resolve_project_for_linkedin(db, company_id=tenant_id, project_id=project_id)
    authorization_url = build_oauth_authorization_url(
        company_id=tenant_id,
        project_id=project.id,
        user_id=current_user.id,
    )
    if redirect:
        return RedirectResponse(url=authorization_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
    return {"authorization_url": authorization_url}


@router.get("/linkedin/oauth/callback")
def linkedin_oauth_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    error_description: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    dashboard_base = "http://localhost:3000/app/channels"
    try:
        from app.core.config import settings

        dashboard_base = settings.linkedin_dashboard_redirect_url
    except Exception:
        pass

    if error:
        reason = quote_plus((error_description or error)[:200])
        return RedirectResponse(url=f"{dashboard_base}?linkedin=error&reason={reason}", status_code=302)

    if not code or not state:
        return RedirectResponse(url=f"{dashboard_base}?linkedin=error&reason=Missing+OAuth+params", status_code=302)

    try:
        state_payload = decode_state(state)
        company_id = UUID(state_payload["company_id"])
        project_id = UUID(state_payload["project_id"])

        token_payload = exchange_code_for_tokens(code)
        access_token = token_payload.get("access_token")
        refresh_token = token_payload.get("refresh_token", "")
        expires_in = int(token_payload.get("expires_in", 3600))
        if not access_token:
            raise HTTPException(status_code=400, detail="LinkedIn token exchange missing access token")

        userinfo = fetch_linkedin_userinfo(access_token)
        linkedin_member_id = str(userinfo.get("sub") or "")
        if not linkedin_member_id:
            raise HTTPException(status_code=400, detail="LinkedIn userinfo missing member id")
        account_name = (
            userinfo.get("name")
            or f"{userinfo.get('given_name', '')} {userinfo.get('family_name', '')}".strip()
            or None
        )

        store_linkedin_account_and_channel(
            db,
            company_id=company_id,
            project_id=project_id,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in_seconds=expires_in,
            linkedin_member_id=linkedin_member_id,
            account_name=account_name,
        )
    except Exception as exc:
        reason = quote_plus(str(exc)[:200])
        return RedirectResponse(url=f"{dashboard_base}?linkedin=error&reason={reason}", status_code=302)

    return RedirectResponse(url=f"{dashboard_base}?linkedin=connected", status_code=302)
