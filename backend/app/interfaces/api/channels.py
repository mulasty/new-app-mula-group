from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models.channel import Channel, ChannelType
from app.domain.models.project import Project
from app.domain.models.user import User, UserRole
from app.interfaces.api.deps import get_current_user, require_roles, require_tenant_id
from app.infrastructure.db.session import get_db

router = APIRouter(prefix="/channels", tags=["channels"])


class ChannelCreateRequest(BaseModel):
    project_id: UUID
    type: str = Field(default=ChannelType.WEBSITE.value)
    name: str | None = Field(default=None, min_length=1, max_length=255)


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
