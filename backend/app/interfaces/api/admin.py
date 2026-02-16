import csv
import io
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.application.services.audit_service import log_audit_event
from app.application.services.feature_flag_service import is_feature_enabled
from app.core.security import create_access_token, create_refresh_token
from app.domain.models.audit_log import AuditLog
from app.domain.models.channel import Channel
from app.domain.models.company import Company
from app.domain.models.company_subscription import CompanySubscription
from app.domain.models.company_usage import CompanyUsage
from app.domain.models.post import Post
from app.domain.models.project import Project
from app.domain.models.publish_event import PublishEvent
from app.domain.models.user import User, UserRole
from app.domain.models.webhook_event import WebhookEvent
from app.interfaces.api.deps import get_current_user, require_platform_admin
from app.interfaces.api.stripe_webhooks import process_stripe_event_payload
from app.infrastructure.db.session import get_db

router = APIRouter(prefix="/admin", tags=["admin"])


def _ensure_admin_panel_enabled(db: Session) -> None:
    if not is_feature_enabled(db, key="beta_admin_panel", tenant_id=None):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Admin panel feature is disabled")


@router.get("/tenants", status_code=status.HTTP_200_OK)
def list_tenants(
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_admin),
) -> dict:
    _ensure_admin_panel_enabled(db)
    rows = db.execute(select(Company).order_by(Company.created_at.desc()).limit(limit)).scalars().all()
    items = []
    for company in rows:
        subscription = db.execute(
            select(CompanySubscription).where(CompanySubscription.company_id == company.id)
        ).scalar_one_or_none()
        usage = db.execute(select(CompanyUsage).where(CompanyUsage.company_id == company.id)).scalar_one_or_none()
        posts_published = db.execute(
            select(func.count(Post.id)).where(Post.company_id == company.id, Post.status.in_(["published", "published_partial"]))
        ).scalar_one()
        items.append(
            {
                "company_id": str(company.id),
                "name": company.name,
                "slug": company.slug,
                "subscription_status": subscription.status if subscription else "n/a",
                "posts_used_current_period": int(usage.posts_used_current_period if usage else 0),
                "published_posts": int(posts_published or 0),
            }
        )
    return {"items": items}


@router.get("/audit-logs", status_code=status.HTTP_200_OK)
def list_audit_logs(
    company_id: UUID | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_admin),
) -> dict:
    _ensure_admin_panel_enabled(db)
    query = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
    if company_id:
        query = query.where(AuditLog.company_id == company_id)
    rows = db.execute(query).scalars().all()
    return {
        "items": [
            {
                "id": str(item.id),
                "company_id": str(item.company_id),
                "action": item.action,
                "metadata_json": item.metadata_json or {},
                "created_at": item.created_at.isoformat(),
            }
            for item in rows
        ]
    }


@router.post("/tenants/{tenant_id}/impersonate", status_code=status.HTTP_201_CREATED)
def impersonate_tenant(
    tenant_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_admin),
) -> dict:
    _ensure_admin_panel_enabled(db)
    target_user = db.execute(
        select(User).where(User.company_id == tenant_id, User.role.in_([UserRole.OWNER.value, UserRole.ADMIN.value]))
    ).scalars().first()
    if target_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target tenant has no owner/admin user")

    access_token = create_access_token(user_id=target_user.id, company_id=target_user.company_id)
    refresh_token = create_refresh_token(user_id=target_user.id, company_id=target_user.company_id)
    log_audit_event(
        db,
        company_id=tenant_id,
        action="admin.impersonation_started",
        metadata={"platform_admin_user_id": str(current_user.id), "target_user_id": str(target_user.id)},
    )
    db.commit()
    return {
        "tenant_id": str(tenant_id),
        "access_token": access_token,
        "refresh_token": refresh_token,
        "target_user": {"id": str(target_user.id), "email": target_user.email, "role": target_user.role},
    }


@router.get("/tenants/{tenant_id}/export", status_code=status.HTTP_200_OK)
def export_tenant_data(
    tenant_id: UUID,
    format: str = Query(default="json", pattern="^(json|csv)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_admin),
):
    _ensure_admin_panel_enabled(db)
    company = db.execute(select(Company).where(Company.id == tenant_id)).scalar_one_or_none()
    if company is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    projects_count = int(db.execute(select(func.count(Project.id)).where(Project.company_id == tenant_id)).scalar_one() or 0)
    channels_count = int(db.execute(select(func.count(Channel.id)).where(Channel.company_id == tenant_id)).scalar_one() or 0)
    posts_count = int(db.execute(select(func.count(Post.id)).where(Post.company_id == tenant_id)).scalar_one() or 0)
    publish_events_count = int(
        db.execute(select(func.count(PublishEvent.id)).where(PublishEvent.company_id == tenant_id)).scalar_one() or 0
    )
    payload = {
        "company_id": str(company.id),
        "name": company.name,
        "slug": company.slug,
        "projects_count": projects_count,
        "channels_count": channels_count,
        "posts_count": posts_count,
        "publish_events_count": publish_events_count,
    }

    log_audit_event(
        db,
        company_id=tenant_id,
        action="admin.export_tenant_data",
        metadata={"requested_by": str(current_user.id), "format": format},
    )
    db.commit()

    if format == "json":
        return payload

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(payload.keys()))
    writer.writeheader()
    writer.writerow(payload)
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="tenant-{tenant_id}.csv"'},
    )


@router.get("/webhooks/events", status_code=status.HTTP_200_OK)
def list_webhook_events(
    provider: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_admin),
) -> dict:
    _ensure_admin_panel_enabled(db)
    query = select(WebhookEvent).order_by(WebhookEvent.created_at.desc()).limit(limit)
    if provider:
        query = query.where(WebhookEvent.provider == provider)
    rows = db.execute(query).scalars().all()
    return {
        "items": [
            {
                "id": str(item.id),
                "provider": item.provider,
                "event_type": item.event_type,
                "external_event_id": item.external_event_id,
                "status": item.status,
                "created_at": item.created_at.isoformat(),
            }
            for item in rows
        ]
    }


@router.post("/webhooks/events/{event_id}/resend", status_code=status.HTTP_202_ACCEPTED)
def resend_webhook_event(
    event_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_admin),
) -> dict:
    _ensure_admin_panel_enabled(db)
    webhook_event = db.execute(select(WebhookEvent).where(WebhookEvent.id == event_id)).scalar_one_or_none()
    if webhook_event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook event not found")
    if webhook_event.provider != "stripe":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only stripe event resend is supported")

    result = process_stripe_event_payload(db, webhook_event.payload_json)
    webhook_event.status = "resent"
    db.add(webhook_event)
    db.commit()
    return {"status": "resent", "result": result}
