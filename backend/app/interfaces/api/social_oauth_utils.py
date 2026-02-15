from uuid import UUID
from urllib.parse import quote_plus

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.domain.models.channel import Channel
from app.domain.models.project import Project
from app.integrations.channel_adapters import get_adapter_capabilities


def resolve_project_for_platform(
    db: Session,
    *,
    company_id: UUID,
    project_id: UUID | None,
    platform_display_name: str,
) -> Project:
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
            detail=f"Create a project before connecting {platform_display_name}",
        )
    return project


def ensure_channel_for_platform(
    db: Session,
    *,
    company_id: UUID,
    project_id: UUID,
    channel_type: str,
    channel_name: str,
) -> Channel:
    capabilities = get_adapter_capabilities(channel_type)
    channel = db.execute(
        select(Channel).where(
            Channel.company_id == company_id,
            Channel.project_id == project_id,
            Channel.type == channel_type,
        )
    ).scalar_one_or_none()
    if channel is None:
        channel = Channel(
            company_id=company_id,
            project_id=project_id,
            type=channel_type,
            name=channel_name.strip() or channel_type.title(),
            status="active",
            capabilities_json=capabilities,
        )
    else:
        channel.name = channel_name.strip() or channel.name
        channel.status = "active"
        channel.capabilities_json = capabilities
    db.add(channel)
    return channel


def build_dashboard_redirect(
    *,
    platform: str,
    success: bool,
    reason: str | None = None,
) -> str:
    base_url = settings.public_app_url.rstrip("/")
    if success:
        return f"{base_url}/app/channels?connected={quote_plus(platform)}"
    reason_param = quote_plus((reason or "OAuth flow failed")[:220])
    return f"{base_url}/app/channels?connected={quote_plus(platform + '_error')}&reason={reason_param}"
