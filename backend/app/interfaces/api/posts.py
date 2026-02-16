import logging
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.services.publishing_service import emit_publish_event, publish_post_async
from app.application.services.audit_service import log_audit_event
from app.application.services.billing_service import enforce_post_limit, increment_post_usage
from app.application.services.feature_flag_service import is_feature_enabled
from app.application.services.template_renderer import render_prompt_template
from app.application.services.platform_ops_service import TENANT_RISK_THRESHOLD, calculate_tenant_risk_score
from app.domain.models.content_template import ContentTemplate
from app.domain.models.post import Post, PostStatus
from app.domain.models.project import Project
from app.domain.models.publish_event import PublishEvent
from app.domain.models.user import User, UserRole
from app.interfaces.api.deps import get_current_user, require_roles, require_tenant_id
from app.infrastructure.db.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/posts", tags=["posts"])


class PostCreateRequest(BaseModel):
    project_id: UUID
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1)
    status: str | None = Field(default=None)


class PostUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    content: str | None = Field(default=None, min_length=1)
    status: str | None = Field(default=None)


class SchedulePostRequest(BaseModel):
    publish_at: datetime


class CreateFromTemplateRequest(BaseModel):
    project_id: UUID
    template_id: UUID
    variables: dict[str, str] = Field(default_factory=dict)
    title: str | None = Field(default=None, min_length=1, max_length=255)
    status: str = Field(default=PostStatus.DRAFT.value)
    publish_at: datetime | None = None


def _enforce_tenant_risk_controls(db: Session, *, tenant_id: UUID) -> None:
    if not is_feature_enabled(db, key="enforce_tenant_risk_controls", tenant_id=tenant_id):
        return
    risk = calculate_tenant_risk_score(db, company_id=tenant_id)
    if risk["risk_score"] >= TENANT_RISK_THRESHOLD:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="Tenant risk threshold exceeded; manual approval is required for publishing",
        )


def _serialize_post(post: Post) -> dict:
    return {
        "id": str(post.id),
        "company_id": str(post.company_id),
        "project_id": str(post.project_id),
        "title": post.title,
        "content": post.content,
        "status": post.status,
        "publish_at": post.publish_at.isoformat() if post.publish_at else None,
        "last_error": post.last_error,
        "created_at": post.created_at.isoformat(),
        "updated_at": post.updated_at.isoformat(),
    }


@router.post("", status_code=status.HTTP_201_CREATED)
def create_post(
    payload: PostCreateRequest,
    db: Session = Depends(get_db),
    tenant_id: UUID = Depends(require_tenant_id),
    current_user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER, UserRole.EDITOR)),
) -> dict:
    enforce_post_limit(db, company_id=tenant_id)
    project = db.execute(
        select(Project).where(Project.id == payload.project_id, Project.company_id == tenant_id)
    ).scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    requested_status = payload.status or PostStatus.DRAFT.value
    if requested_status != PostStatus.DRAFT.value:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only draft status is allowed on create")

    post = Post(
        company_id=tenant_id,
        project_id=payload.project_id,
        title=payload.title.strip(),
        content=payload.content.strip(),
        status=PostStatus.DRAFT.value,
    )
    db.add(post)
    db.flush()
    increment_post_usage(db, company_id=tenant_id, amount=1)
    log_audit_event(
        db,
        company_id=tenant_id,
        action="post.created",
        metadata={"post_id": str(post.id), "project_id": str(post.project_id), "user_id": str(current_user.id)},
    )
    db.commit()
    db.refresh(post)
    return _serialize_post(post)


@router.post("/from-template", status_code=status.HTTP_201_CREATED)
def create_post_from_template(
    payload: CreateFromTemplateRequest,
    db: Session = Depends(get_db),
    tenant_id: UUID = Depends(require_tenant_id),
    current_user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER, UserRole.EDITOR)),
) -> dict:
    enforce_post_limit(db, company_id=tenant_id)
    project = db.execute(
        select(Project).where(Project.id == payload.project_id, Project.company_id == tenant_id)
    ).scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    template = db.execute(
        select(ContentTemplate).where(
            ContentTemplate.id == payload.template_id,
            ContentTemplate.company_id == tenant_id,
            ContentTemplate.project_id == payload.project_id,
        )
    ).scalar_one_or_none()
    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")

    variables = {**(payload.variables or {}), "project_name": project.name, "template_tone": template.tone}
    generated_body = render_prompt_template(template.prompt_template, variables).strip()
    if not generated_body:
        generated_body = render_prompt_template(template.content_structure, variables).strip() or template.prompt_template

    requested_status = payload.status or PostStatus.DRAFT.value
    if requested_status not in {PostStatus.DRAFT.value, PostStatus.SCHEDULED.value}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only draft or scheduled allowed")

    publish_at = payload.publish_at if payload.publish_at else None
    if publish_at is not None and publish_at.tzinfo is None:
        publish_at = publish_at.replace(tzinfo=UTC)
    if requested_status == PostStatus.SCHEDULED.value and publish_at is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="publish_at is required for scheduled posts")

    title = payload.title.strip() if payload.title else f"{project.name} | {template.name}"

    post = Post(
        company_id=tenant_id,
        project_id=payload.project_id,
        title=title,
        content=generated_body,
        status=requested_status,
        publish_at=publish_at,
    )
    db.add(post)
    db.flush()
    increment_post_usage(db, company_id=tenant_id, amount=1)

    log_audit_event(
        db,
        company_id=tenant_id,
        action="post.created_from_template",
        metadata={"post_id": str(post.id), "template_id": str(template.id), "user_id": str(current_user.id)},
    )

    if requested_status == PostStatus.SCHEDULED.value and publish_at is not None:
        emit_publish_event(
            db,
            company_id=post.company_id,
            project_id=post.project_id,
            post_id=post.id,
            event_type="PostScheduled",
            status="ok",
            metadata_json={"publish_at": publish_at.isoformat(), "source": "template"},
        )

    db.commit()
    db.refresh(post)
    return _serialize_post(post)


@router.get("", status_code=status.HTTP_200_OK)
def list_posts(
    project_id: UUID | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    tenant_id: UUID = Depends(require_tenant_id),
    current_user: User = Depends(get_current_user),
) -> dict:
    query = select(Post).where(Post.company_id == tenant_id)
    if project_id is not None:
        query = query.where(Post.project_id == project_id)
    if status_filter is not None:
        query = query.where(Post.status == status_filter)

    rows = db.execute(query.order_by(Post.created_at.desc())).scalars().all()
    return {"items": [_serialize_post(row) for row in rows]}


@router.patch("/{post_id}", status_code=status.HTTP_200_OK)
def update_post(
    post_id: UUID,
    payload: PostUpdateRequest,
    db: Session = Depends(get_db),
    tenant_id: UUID = Depends(require_tenant_id),
    current_user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER, UserRole.EDITOR)),
) -> dict:
    post = db.execute(select(Post).where(Post.id == post_id, Post.company_id == tenant_id)).scalar_one_or_none()
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    if payload.title is not None:
        post.title = payload.title.strip()
    if payload.content is not None:
        post.content = payload.content.strip()
    if payload.status is not None:
        if payload.status not in {PostStatus.DRAFT.value, PostStatus.SCHEDULED.value}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Status can only be draft or scheduled via this endpoint",
            )
        post.status = payload.status

    db.add(post)
    db.commit()
    db.refresh(post)
    return _serialize_post(post)


@router.post("/{post_id}/schedule", status_code=status.HTTP_200_OK)
def schedule_post(
    post_id: UUID,
    payload: SchedulePostRequest,
    db: Session = Depends(get_db),
    tenant_id: UUID = Depends(require_tenant_id),
    current_user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN)),
) -> dict:
    _enforce_tenant_risk_controls(db, tenant_id=tenant_id)
    post = db.execute(select(Post).where(Post.id == post_id, Post.company_id == tenant_id)).scalar_one_or_none()
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    publish_at = payload.publish_at if payload.publish_at.tzinfo else payload.publish_at.replace(tzinfo=UTC)
    post.status = PostStatus.SCHEDULED.value
    post.publish_at = publish_at
    post.last_error = None

    emit_publish_event(
        db,
        company_id=post.company_id,
        project_id=post.project_id,
        post_id=post.id,
        event_type="PostScheduled",
        status="ok",
        metadata_json={"publish_at": publish_at.isoformat()},
    )
    db.add(post)
    db.commit()
    db.refresh(post)

    logger.info(
        "post_scheduled company_id=%s post_id=%s project_id=%s publish_at=%s user_id=%s",
        post.company_id,
        post.id,
        post.project_id,
        publish_at.isoformat(),
        current_user.id,
    )
    return _serialize_post(post)


@router.post("/{post_id}/publish-now", status_code=status.HTTP_200_OK)
def publish_now(
    post_id: UUID,
    db: Session = Depends(get_db),
    tenant_id: UUID = Depends(require_tenant_id),
    current_user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN)),
) -> dict:
    _enforce_tenant_risk_controls(db, tenant_id=tenant_id)
    post = db.execute(select(Post).where(Post.id == post_id, Post.company_id == tenant_id)).scalar_one_or_none()
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    now = datetime.now(UTC)
    post.status = PostStatus.SCHEDULED.value
    post.publish_at = now
    post.last_error = None

    emit_publish_event(
        db,
        company_id=post.company_id,
        project_id=post.project_id,
        post_id=post.id,
        event_type="PostPublishNowRequested",
        status="ok",
        metadata_json={"publish_at": now.isoformat()},
    )
    db.add(post)
    log_audit_event(
        db,
        company_id=tenant_id,
        action="post.publish_now_requested",
        metadata={"post_id": str(post.id), "project_id": str(post.project_id), "user_id": str(current_user.id)},
    )
    db.commit()
    db.refresh(post)

    publish_post_async(post.company_id, post.id)
    logger.info(
        "post_publish_now_requested company_id=%s post_id=%s project_id=%s user_id=%s",
        post.company_id,
        post.id,
        post.project_id,
        current_user.id,
    )
    return _serialize_post(post)


@router.get("/{post_id}/timeline", status_code=status.HTTP_200_OK)
def get_post_timeline(
    post_id: UUID,
    db: Session = Depends(get_db),
    tenant_id: UUID = Depends(require_tenant_id),
    current_user: User = Depends(get_current_user),
) -> dict:
    exists = db.execute(select(Post.id).where(Post.id == post_id, Post.company_id == tenant_id)).scalar_one_or_none()
    if exists is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    rows = db.execute(
        select(PublishEvent)
        .where(PublishEvent.company_id == tenant_id, PublishEvent.post_id == post_id)
        .order_by(PublishEvent.created_at.desc())
    ).scalars().all()

    return {
        "items": [
            {
                "id": str(row.id),
                "company_id": str(row.company_id),
                "project_id": str(row.project_id),
                "post_id": str(row.post_id),
                "channel_id": str(row.channel_id) if row.channel_id else None,
                "event_type": row.event_type,
                "status": row.status,
                "attempt": row.attempt,
                "metadata_json": row.metadata_json,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ]
    }
