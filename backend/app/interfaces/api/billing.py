from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.application.services.audit_service import log_audit_event
from app.application.services.billing_service import bootstrap_company_billing
from app.application.services.feature_flag_service import is_feature_enabled
from app.application.services.stripe_checkout_service import create_checkout_session
from app.domain.models.billing_event import BillingEvent
from app.domain.models.channel import Channel
from app.domain.models.company_subscription import CompanySubscription
from app.domain.models.company_usage import CompanyUsage
from app.domain.models.project import Project
from app.domain.models.subscription_plan import SubscriptionPlan
from app.domain.models.user import User
from app.interfaces.api.deps import get_current_user, require_tenant_id
from app.infrastructure.db.session import get_db

router = APIRouter(prefix="/billing", tags=["billing"])
public_router = APIRouter(prefix="/public", tags=["public"])


class CheckoutRequest(BaseModel):
    plan_name: str
    success_url: str | None = None
    cancel_url: str | None = None


class PlanUpdateRequest(BaseModel):
    plan_name: str


class CancelSubscriptionRequest(BaseModel):
    immediate: bool = False


def _serialize_plan(plan: SubscriptionPlan) -> dict:
    return {
        "id": str(plan.id),
        "name": plan.name,
        "monthly_price": float(Decimal(plan.monthly_price)),
        "max_projects": plan.max_projects,
        "max_posts_per_month": plan.max_posts_per_month,
        "max_connectors": plan.max_connectors,
    }


def _log_billing_event(
    db: Session,
    *,
    tenant_id: UUID,
    event_type: str,
    message: str,
    metadata: dict | None = None,
) -> None:
    db.add(
        BillingEvent(
            company_id=tenant_id,
            event_type=event_type,
            message=message,
            metadata_json=metadata or {},
        )
    )


@public_router.get("/plans", status_code=status.HTTP_200_OK)
def list_public_plans(db: Session = Depends(get_db)) -> dict:
    if not is_feature_enabled(db, key="beta_public_pricing", tenant_id=None):
        return {"items": [], "beta_disabled": True}
    plans = db.execute(select(SubscriptionPlan).order_by(SubscriptionPlan.monthly_price.asc())).scalars().all()
    return {"items": [_serialize_plan(plan) for plan in plans]}


@router.get("/plans", status_code=status.HTTP_200_OK)
def list_plans(
    db: Session = Depends(get_db),
    tenant_id: UUID = Depends(require_tenant_id),
    current_user: User = Depends(get_current_user),
) -> dict:
    bootstrap_company_billing(db, company_id=tenant_id)
    db.commit()
    return list_public_plans(db)


@router.get("/current", status_code=status.HTTP_200_OK)
def get_current_plan(
    db: Session = Depends(get_db),
    tenant_id: UUID = Depends(require_tenant_id),
    current_user: User = Depends(get_current_user),
) -> dict:
    bootstrap_company_billing(db, company_id=tenant_id)
    db.commit()
    subscription = db.execute(
        select(CompanySubscription).where(CompanySubscription.company_id == tenant_id)
    ).scalar_one()
    plan = db.execute(select(SubscriptionPlan).where(SubscriptionPlan.id == subscription.plan_id)).scalar_one()
    usage = db.execute(select(CompanyUsage).where(CompanyUsage.company_id == tenant_id)).scalar_one_or_none()
    projects_count = int(
        db.execute(select(func.count(Project.id)).where(Project.company_id == tenant_id)).scalar_one() or 0
    )
    connectors_count = int(
        db.execute(select(func.count(Channel.id)).where(Channel.company_id == tenant_id)).scalar_one() or 0
    )
    now = datetime.now(UTC)
    current_period_end = subscription.current_period_end
    in_grace_period = subscription.status == "grace_period"
    expired = bool(current_period_end and current_period_end <= now and subscription.status in {"grace_period", "past_due"})
    if expired:
        subscription.status = "expired"
        db.add(subscription)
        db.commit()
    days_left = 0
    if current_period_end and current_period_end > now:
        days_left = max(0, int((current_period_end - now).total_seconds() // 86400))

    posts_used = int(usage.posts_used_current_period if usage else 0)
    posts_pct = (posts_used / max(1, int(plan.max_posts_per_month))) * 100
    projects_pct = (projects_count / max(1, int(plan.max_projects))) * 100
    connectors_pct = (connectors_count / max(1, int(plan.max_connectors))) * 100

    return {
        "subscription": {
            "id": str(subscription.id),
            "status": subscription.status,
            "current_period_end": subscription.current_period_end.isoformat() if subscription.current_period_end else None,
            "stripe_customer_id": subscription.stripe_customer_id,
            "stripe_subscription_id": subscription.stripe_subscription_id,
        },
        "plan": _serialize_plan(plan),
        "usage": {
            "posts_used_current_period": posts_used,
            "projects_count": projects_count,
            "connectors_count": connectors_count,
            "posts_usage_percent": round(posts_pct, 2),
            "projects_usage_percent": round(projects_pct, 2),
            "connectors_usage_percent": round(connectors_pct, 2),
        },
        "lifecycle": {
            "in_grace_period": in_grace_period,
            "expired": expired,
            "days_left_in_period": days_left,
        }
    }


@router.post("/checkout-session", status_code=status.HTTP_201_CREATED)
def create_checkout(
    payload: CheckoutRequest,
    db: Session = Depends(get_db),
    tenant_id: UUID = Depends(require_tenant_id),
    current_user: User = Depends(get_current_user),
) -> dict:
    if not is_feature_enabled(db, key="beta_public_pricing", tenant_id=tenant_id):
        return {"checkout_url": None, "session_id": None, "beta_disabled": True}
    session = create_checkout_session(
        db,
        company_id=tenant_id,
        plan_name=payload.plan_name,
        success_url=payload.success_url,
        cancel_url=payload.cancel_url,
    )
    log_audit_event(
        db,
        company_id=tenant_id,
        action="subscription.checkout_started",
        metadata={"plan_name": payload.plan_name, "user_id": str(current_user.id), "session_id": session.session_id},
    )
    db.commit()
    return {"checkout_url": session.checkout_url, "session_id": session.session_id}


@router.post("/upgrade", status_code=status.HTTP_200_OK)
def upgrade_plan(
    payload: PlanUpdateRequest,
    db: Session = Depends(get_db),
    tenant_id: UUID = Depends(require_tenant_id),
    current_user: User = Depends(get_current_user),
) -> dict:
    bootstrap_company_billing(db, company_id=tenant_id)
    subscription = db.execute(
        select(CompanySubscription).where(CompanySubscription.company_id == tenant_id)
    ).scalar_one()
    plan = db.execute(
        select(SubscriptionPlan).where(SubscriptionPlan.name == payload.plan_name.strip())
    ).scalar_one_or_none()
    if plan is None:
        return {"updated": False, "message": "Plan not found"}

    subscription.plan_id = plan.id
    subscription.status = "active"
    if subscription.current_period_end is None:
        subscription.current_period_end = datetime.now(UTC) + timedelta(days=30)
    db.add(subscription)
    _log_billing_event(
        db,
        tenant_id=tenant_id,
        event_type="subscription.upgraded",
        message=f"Plan upgraded to {plan.name}",
        metadata={"plan_name": plan.name, "user_id": str(current_user.id)},
    )
    log_audit_event(
        db,
        company_id=tenant_id,
        action="subscription.upgraded",
        metadata={"plan_name": plan.name, "user_id": str(current_user.id)},
    )
    db.commit()
    return {"updated": True, "plan": _serialize_plan(plan)}


@router.post("/downgrade", status_code=status.HTTP_200_OK)
def downgrade_plan(
    payload: PlanUpdateRequest,
    db: Session = Depends(get_db),
    tenant_id: UUID = Depends(require_tenant_id),
    current_user: User = Depends(get_current_user),
) -> dict:
    bootstrap_company_billing(db, company_id=tenant_id)
    subscription = db.execute(
        select(CompanySubscription).where(CompanySubscription.company_id == tenant_id)
    ).scalar_one()
    plan = db.execute(
        select(SubscriptionPlan).where(SubscriptionPlan.name == payload.plan_name.strip())
    ).scalar_one_or_none()
    if plan is None:
        return {"updated": False, "message": "Plan not found"}

    subscription.plan_id = plan.id
    subscription.status = "active"
    db.add(subscription)
    _log_billing_event(
        db,
        tenant_id=tenant_id,
        event_type="subscription.downgraded",
        message=f"Plan changed to {plan.name}",
        metadata={"plan_name": plan.name, "user_id": str(current_user.id)},
    )
    log_audit_event(
        db,
        company_id=tenant_id,
        action="subscription.downgraded",
        metadata={"plan_name": plan.name, "user_id": str(current_user.id)},
    )
    db.commit()
    return {"updated": True, "plan": _serialize_plan(plan)}


@router.post("/cancel", status_code=status.HTTP_200_OK)
def cancel_subscription(
    payload: CancelSubscriptionRequest,
    db: Session = Depends(get_db),
    tenant_id: UUID = Depends(require_tenant_id),
    current_user: User = Depends(get_current_user),
) -> dict:
    bootstrap_company_billing(db, company_id=tenant_id)
    subscription = db.execute(
        select(CompanySubscription).where(CompanySubscription.company_id == tenant_id)
    ).scalar_one()
    now = datetime.now(UTC)
    if payload.immediate:
        subscription.status = "canceled"
        subscription.current_period_end = now
    else:
        subscription.status = "grace_period"
        if subscription.current_period_end is None or subscription.current_period_end < now:
            subscription.current_period_end = now + timedelta(days=14)
    db.add(subscription)
    _log_billing_event(
        db,
        tenant_id=tenant_id,
        event_type="subscription.canceled",
        message="Subscription cancellation requested",
        metadata={"immediate": payload.immediate, "user_id": str(current_user.id)},
    )
    log_audit_event(
        db,
        company_id=tenant_id,
        action="subscription.canceled",
        metadata={"immediate": payload.immediate, "user_id": str(current_user.id)},
    )
    db.commit()
    return {"updated": True, "status": subscription.status}


@router.post("/reactivate", status_code=status.HTTP_200_OK)
def reactivate_subscription(
    db: Session = Depends(get_db),
    tenant_id: UUID = Depends(require_tenant_id),
    current_user: User = Depends(get_current_user),
) -> dict:
    bootstrap_company_billing(db, company_id=tenant_id)
    subscription = db.execute(
        select(CompanySubscription).where(CompanySubscription.company_id == tenant_id)
    ).scalar_one()
    subscription.status = "active"
    if subscription.current_period_end is None or subscription.current_period_end <= datetime.now(UTC):
        subscription.current_period_end = datetime.now(UTC) + timedelta(days=30)
    db.add(subscription)
    _log_billing_event(
        db,
        tenant_id=tenant_id,
        event_type="subscription.reactivated",
        message="Subscription reactivated",
        metadata={"user_id": str(current_user.id)},
    )
    log_audit_event(
        db,
        company_id=tenant_id,
        action="subscription.reactivated",
        metadata={"user_id": str(current_user.id)},
    )
    db.commit()
    return {"updated": True, "status": subscription.status}


@router.get("/history", status_code=status.HTTP_200_OK)
def billing_history(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    tenant_id: UUID = Depends(require_tenant_id),
    current_user: User = Depends(get_current_user),
) -> dict:
    rows = db.execute(
        select(BillingEvent)
        .where(BillingEvent.company_id == tenant_id)
        .order_by(BillingEvent.created_at.desc())
        .limit(limit)
    ).scalars().all()
    return {
        "items": [
            {
                "id": str(row.id),
                "event_type": row.event_type,
                "message": row.message,
                "metadata_json": row.metadata_json or {},
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ]
    }
