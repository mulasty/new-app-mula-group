import logging
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.services.publishing_service import emit_publish_event, publish_post_async
from app.application.services.audit_service import log_audit_event
from app.application.services.billing_service import enforce_billing_write_access, enforce_post_limit, increment_post_usage
from app.application.services.feature_flag_service import is_feature_enabled
from app.application.services.post_quality_service import (
    create_post_quality_report,
    evaluate_post_quality,
    extract_recommendations,
    get_latest_quality_report,
    resolve_brand_profile,
)
from app.application.services.template_renderer import render_prompt_template
from app.application.services.platform_ops_service import TENANT_RISK_THRESHOLD, calculate_tenant_risk_score
from app.domain.models.content_template import ContentTemplate
from app.domain.models.post import Post, PostStatus
from app.domain.models.post_quality_report import PostQualityReport
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


class PostRejectRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class PostQualityCheckRequest(BaseModel):
    brand_profile_id: UUID | None = None
    recent_posts_window: int = Field(default=20, ge=5, le=100)


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
    quality = getattr(post, "_quality_report", None)
    quality_payload = None
    if quality is not None:
        quality_payload = {
            "score": quality.score,
            "risk_level": quality.risk_level,
            "issues": quality.issues or [],
            "recommendations": extract_recommendations(quality.issues or []),
            "created_at": quality.created_at.isoformat(),
        }
    return {
        "id": str(post.id),
        "company_id": str(post.company_id),
        "project_id": str(post.project_id),
        "title": post.title,
        "content": post.content,
        "status": post.status,
        "publish_at": post.publish_at.isoformat() if post.publish_at else None,
        "last_error": post.last_error,
        "quality_report": quality_payload,
        "created_at": post.created_at.isoformat(),
        "updated_at": post.updated_at.isoformat(),
    }


def _attach_quality_reports(db: Session, *, tenant_id: UUID, rows: list[Post]) -> None:
    if not rows:
        return
    post_ids = [row.id for row in rows]
    reports = db.execute(
        select(PostQualityReport)
        .where(PostQualityReport.company_id == tenant_id, PostQualityReport.post_id.in_(post_ids))
        .order_by(PostQualityReport.post_id.asc(), PostQualityReport.created_at.desc())
    ).scalars().all()
    latest_by_post: dict[UUID, PostQualityReport] = {}
    for report in reports:
        if report.post_id not in latest_by_post:
            latest_by_post[report.post_id] = report
    for row in rows:
        setattr(row, "_quality_report", latest_by_post.get(row.id))


def _run_quality_check(
    db: Session,
    *,
    post: Post,
    tenant_id: UUID,
    brand_profile_id: UUID | None,
    recent_posts_window: int = 20,
) -> PostQualityReport:
    profile = resolve_brand_profile(
        db,
        tenant_id=tenant_id,
        project_id=post.project_id,
        brand_profile_id=brand_profile_id,
    )
    recent_rows = db.execute(
        select(Post)
        .where(
            Post.company_id == tenant_id,
            Post.project_id == post.project_id,
            Post.id != post.id,
        )
        .order_by(Post.created_at.desc())
        .limit(recent_posts_window)
    ).scalars().all()
    result = evaluate_post_quality(
        title=post.title,
        body=post.content,
        brand_profile=profile,
        recent_posts=recent_rows,
    )
    return create_post_quality_report(db, post=post, result=result)


def _enforce_quality_gate(db: Session, *, tenant_id: UUID, post: Post) -> None:
    if not is_feature_enabled(db, key="v1_ai_quality_gate", tenant_id=tenant_id):
        return
    if post.status == PostStatus.NEEDS_APPROVAL.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Post requires manual approval before publishing",
        )
    report = get_latest_quality_report(db, tenant_id=tenant_id, post_id=post.id)
    if report is None:
        report = _run_quality_check(db, post=post, tenant_id=tenant_id, brand_profile_id=None)
    has_block = any(str(item.get("severity")) == "block" for item in (report.issues or []))
    if report.risk_level == "high" or has_block:
        post.status = PostStatus.NEEDS_APPROVAL.value
        post.last_error = "Quality gate blocked publish. Approval required."
        db.add(post)
        emit_publish_event(
            db,
            company_id=post.company_id,
            project_id=post.project_id,
            post_id=post.id,
            event_type="PostNeedsApproval",
            status="error",
            metadata_json={
                "quality_score": report.score,
                "risk_level": report.risk_level,
                "issues": report.issues or [],
            },
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Quality gate blocked publish. Review issues and approve post first.",
        )


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
    _attach_quality_reports(db, tenant_id=tenant_id, rows=rows)
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
        if payload.status not in {PostStatus.DRAFT.value, PostStatus.SCHEDULED.value, PostStatus.NEEDS_APPROVAL.value}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Status can only be draft, scheduled or needs_approval via this endpoint",
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
    enforce_billing_write_access(db, company_id=tenant_id, action="schedule_post")
    _enforce_tenant_risk_controls(db, tenant_id=tenant_id)
    post = db.execute(select(Post).where(Post.id == post_id, Post.company_id == tenant_id)).scalar_one_or_none()
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    _enforce_quality_gate(db, tenant_id=tenant_id, post=post)

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
    enforce_billing_write_access(db, company_id=tenant_id, action="publish_post")
    _enforce_tenant_risk_controls(db, tenant_id=tenant_id)
    post = db.execute(select(Post).where(Post.id == post_id, Post.company_id == tenant_id)).scalar_one_or_none()
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    _enforce_quality_gate(db, tenant_id=tenant_id, post=post)

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


@router.post("/{post_id}/quality-check", status_code=status.HTTP_200_OK)
def quality_check_post(
    post_id: UUID,
    payload: PostQualityCheckRequest,
    db: Session = Depends(get_db),
    tenant_id: UUID = Depends(require_tenant_id),
    current_user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER, UserRole.EDITOR)),
) -> dict:
    if not is_feature_enabled(db, key="v1_ai_quality_engine", tenant_id=tenant_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI quality engine disabled")
    post = db.execute(select(Post).where(Post.id == post_id, Post.company_id == tenant_id)).scalar_one_or_none()
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    report = _run_quality_check(
        db,
        post=post,
        tenant_id=tenant_id,
        brand_profile_id=payload.brand_profile_id,
        recent_posts_window=payload.recent_posts_window,
    )
    if report.risk_level == "high" or any(str(item.get("severity")) == "block" for item in (report.issues or [])):
        post.status = PostStatus.NEEDS_APPROVAL.value
        post.last_error = "Quality gate flagged this post for manual approval."
    else:
        if post.status == PostStatus.NEEDS_APPROVAL.value:
            post.status = PostStatus.DRAFT.value
            post.last_error = None
    db.add(post)
    log_audit_event(
        db,
        company_id=tenant_id,
        action="post.quality_checked",
        metadata={"post_id": str(post.id), "project_id": str(post.project_id), "user_id": str(current_user.id)},
    )
    db.commit()
    return {
        "post_id": str(post.id),
        "score": report.score,
        "risk_level": report.risk_level,
        "issues": report.issues or [],
        "recommendations": extract_recommendations(report.issues or []),
        "status": post.status,
        "created_at": report.created_at.isoformat(),
    }


@router.get("/{post_id}/quality-report", status_code=status.HTTP_200_OK)
def get_post_quality_report(
    post_id: UUID,
    db: Session = Depends(get_db),
    tenant_id: UUID = Depends(require_tenant_id),
    current_user: User = Depends(get_current_user),
) -> dict:
    if not is_feature_enabled(db, key="v1_ai_quality_engine", tenant_id=tenant_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI quality engine disabled")
    exists = db.execute(select(Post.id).where(Post.id == post_id, Post.company_id == tenant_id)).scalar_one_or_none()
    if exists is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    report = get_latest_quality_report(db, tenant_id=tenant_id, post_id=post_id)
    if report is None:
        return {"post_id": str(post_id), "report": None}
    return {
        "post_id": str(post_id),
        "report": {
            "score": report.score,
            "risk_level": report.risk_level,
            "issues": report.issues or [],
            "recommendations": extract_recommendations(report.issues or []),
            "created_at": report.created_at.isoformat(),
        },
    }


@router.post("/{post_id}/approve", status_code=status.HTTP_200_OK)
def approve_post(
    post_id: UUID,
    db: Session = Depends(get_db),
    tenant_id: UUID = Depends(require_tenant_id),
    current_user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN)),
) -> dict:
    post = db.execute(select(Post).where(Post.id == post_id, Post.company_id == tenant_id)).scalar_one_or_none()
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    if post.status != PostStatus.NEEDS_APPROVAL.value:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Post is not awaiting approval")
    post.status = PostStatus.DRAFT.value
    post.last_error = None
    db.add(post)
    log_audit_event(
        db,
        company_id=tenant_id,
        action="post.approved",
        metadata={"post_id": str(post.id), "project_id": str(post.project_id), "user_id": str(current_user.id)},
    )
    db.commit()
    db.refresh(post)
    return _serialize_post(post)


@router.post("/{post_id}/reject", status_code=status.HTTP_200_OK)
def reject_post(
    post_id: UUID,
    payload: PostRejectRequest,
    db: Session = Depends(get_db),
    tenant_id: UUID = Depends(require_tenant_id),
    current_user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN)),
) -> dict:
    post = db.execute(select(Post).where(Post.id == post_id, Post.company_id == tenant_id)).scalar_one_or_none()
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    post.status = PostStatus.NEEDS_APPROVAL.value
    post.last_error = payload.reason.strip()
    db.add(post)
    log_audit_event(
        db,
        company_id=tenant_id,
        action="post.rejected",
        metadata={
            "post_id": str(post.id),
            "project_id": str(post.project_id),
            "reason": payload.reason.strip(),
            "user_id": str(current_user.id),
        },
    )
    db.commit()
    db.refresh(post)
    return _serialize_post(post)
