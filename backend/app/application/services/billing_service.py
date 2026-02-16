from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.models.channel import Channel
from app.domain.models.company_subscription import CompanySubscription
from app.domain.models.company_usage import CompanyUsage
from app.domain.models.post import Post
from app.domain.models.project import Project
from app.domain.models.subscription_plan import SubscriptionPlan
from app.core.config import settings
from app.application.services.feature_flag_service import is_feature_enabled

PLAN_LIMIT_ERROR = {
    "error_code": "PLAN_LIMIT_EXCEEDED",
    "message": "Upgrade your plan.",
}

BILLING_REQUIRED_ERROR = {
    "error_code": "BILLING_REQUIRED",
    "message": "Billing action required. Open billing portal to restore write access.",
}


def _resolve_plan_context(db: Session, *, company_id: UUID) -> tuple[CompanySubscription | None, SubscriptionPlan | None]:
    company_subscription = db.execute(
        select(CompanySubscription).where(CompanySubscription.company_id == company_id)
    ).scalar_one_or_none()
    if company_subscription is None:
        return None, None
    plan = db.execute(select(SubscriptionPlan).where(SubscriptionPlan.id == company_subscription.plan_id)).scalar_one_or_none()
    return company_subscription, plan


def seed_plan_stripe_mapping(db: Session) -> None:
    env_mapping = {
        "starter": settings.stripe_price_id_starter,
        "pro": settings.stripe_price_id_pro,
        "enterprise": settings.stripe_price_id_enterprise,
    }
    plans = db.execute(select(SubscriptionPlan)).scalars().all()
    for plan in plans:
        env_price_id = env_mapping.get(plan.name.strip().lower())
        if env_price_id:
            if plan.stripe_price_id != env_price_id:
                plan.stripe_price_id = env_price_id
                db.add(plan)
            continue
        # Dev fallback placeholder mapping keeps local billing flows testable.
        if not plan.stripe_price_id:
            slug = plan.name.strip().lower().replace(" ", "_")
            plan.stripe_price_id = f"price_dev_{slug}"
            db.add(plan)


def _normalize_subscription_status(subscription: CompanySubscription | None) -> str:
    if subscription is None:
        return "active"
    raw = (subscription.status or "active").strip().lower()
    if raw == "grace_period":
        return "past_due"
    return raw


def enforce_billing_write_access(db: Session, *, company_id: UUID, action: str) -> None:
    if not is_feature_enabled(db, key="v1_billing_enforcement", tenant_id=company_id):
        return
    subscription, _ = _resolve_plan_context(db, company_id=company_id)
    if subscription is None:
        return
    now = datetime.now(UTC)
    state = _normalize_subscription_status(subscription)
    grace_end = subscription.grace_period_end

    if state in {"active", "trialing"}:
        return

    if state == "past_due":
        within_grace = bool(grace_end and grace_end > now)
        if within_grace and settings.billing_past_due_allow_write:
            if action == "add_connector" and settings.billing_restrict_connectors_in_grace:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=BILLING_REQUIRED_ERROR)
            return
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=BILLING_REQUIRED_ERROR)

    if state in {"unpaid", "canceled", "incomplete", "expired"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=BILLING_REQUIRED_ERROR)


def get_billing_status_payload(db: Session, *, company_id: UUID) -> dict:
    subscription, plan = _resolve_plan_context(db, company_id=company_id)
    usage = _ensure_usage_row(db, company_id=company_id)
    now = datetime.now(UTC)

    status_value = _normalize_subscription_status(subscription)
    grace_active = bool(subscription and subscription.grace_period_end and subscription.grace_period_end > now)
    grace_days_left = 0
    if subscription and subscription.grace_period_end and subscription.grace_period_end > now:
        grace_days_left = int((subscription.grace_period_end - now).total_seconds() // 86400)
    if grace_days_left < 0:
        grace_days_left = 0

    return {
        "status": status_value,
        "grace_active": grace_active,
        "grace_period_end": subscription.grace_period_end.isoformat() if subscription and subscription.grace_period_end else None,
        "grace_days_left": grace_days_left,
        "current_period_start": subscription.current_period_start.isoformat() if subscription and subscription.current_period_start else None,
        "current_period_end": subscription.current_period_end.isoformat() if subscription and subscription.current_period_end else None,
        "cancel_at_period_end": bool(subscription.cancel_at_period_end) if subscription else False,
        "last_invoice_status": (subscription.last_invoice_status if subscription else None),
        "last_payment_error": (subscription.last_payment_error if subscription else None),
        "plan": (
            {
                "id": str(plan.id),
                "name": plan.name,
                "monthly_price": float(plan.monthly_price),
                "max_projects": plan.max_projects,
                "max_posts_per_month": plan.max_posts_per_month,
                "max_connectors": plan.max_connectors,
            }
            if plan
            else None
        ),
        "usage": {
            "posts_used_current_period": int(usage.posts_used_current_period or 0),
            "period_started_at": usage.period_started_at.isoformat() if usage.period_started_at else None,
        },
    }


def _ensure_usage_row(db: Session, *, company_id: UUID) -> CompanyUsage:
    usage = db.execute(select(CompanyUsage).where(CompanyUsage.company_id == company_id)).scalar_one_or_none()
    if usage is not None:
        return usage
    usage = CompanyUsage(company_id=company_id, posts_used_current_period=0)
    db.add(usage)
    db.flush()
    return usage


def enforce_project_limit(db: Session, *, company_id: UUID) -> None:
    enforce_billing_write_access(db, company_id=company_id, action="create_project")
    _, plan = _resolve_plan_context(db, company_id=company_id)
    if plan is None:
        return
    current_projects = db.execute(
        select(func.count(Project.id)).where(Project.company_id == company_id)
    ).scalar_one()
    if int(current_projects or 0) >= int(plan.max_projects):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=PLAN_LIMIT_ERROR)


def enforce_connector_limit(db: Session, *, company_id: UUID) -> None:
    enforce_billing_write_access(db, company_id=company_id, action="add_connector")
    _, plan = _resolve_plan_context(db, company_id=company_id)
    if plan is None:
        return
    current_connectors = db.execute(
        select(func.count(Channel.id)).where(Channel.company_id == company_id)
    ).scalar_one()
    if int(current_connectors or 0) >= int(plan.max_connectors):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=PLAN_LIMIT_ERROR)


def enforce_post_limit(db: Session, *, company_id: UUID) -> None:
    enforce_billing_write_access(db, company_id=company_id, action="create_post")
    subscription, plan = _resolve_plan_context(db, company_id=company_id)
    if plan is None:
        return

    usage = _ensure_usage_row(db, company_id=company_id)
    now = datetime.now(UTC)
    period_end = subscription.current_period_end if subscription is not None else None

    if period_end is not None and period_end <= now:
        usage.posts_used_current_period = 0
        usage.period_started_at = now
        usage.updated_at = now
        if subscription is not None:
            subscription.current_period_end = now + timedelta(days=30)
            db.add(subscription)
        db.add(usage)
        db.flush()

    if int(usage.posts_used_current_period or 0) >= int(plan.max_posts_per_month):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=PLAN_LIMIT_ERROR)


def increment_post_usage(db: Session, *, company_id: UUID, amount: int = 1) -> None:
    usage = _ensure_usage_row(db, company_id=company_id)
    usage.posts_used_current_period = int(usage.posts_used_current_period or 0) + int(amount)
    usage.updated_at = datetime.now(UTC)
    db.add(usage)


def reset_monthly_post_usage(db: Session, *, now: datetime | None = None) -> int:
    current_time = now or datetime.now(UTC)
    rows = db.execute(
        select(CompanySubscription).where(
            CompanySubscription.current_period_end.is_not(None),
            CompanySubscription.current_period_end <= current_time,
        )
    ).scalars().all()

    updated = 0
    for subscription in rows:
        usage = _ensure_usage_row(db, company_id=subscription.company_id)
        usage.posts_used_current_period = 0
        usage.period_started_at = current_time
        usage.updated_at = current_time
        subscription.current_period_end = current_time + timedelta(days=30)
        db.add(usage)
        db.add(subscription)
        updated += 1
    return updated


def bootstrap_company_billing(db: Session, *, company_id: UUID) -> None:
    seed_plan_stripe_mapping(db)
    existing_subscription = db.execute(
        select(CompanySubscription).where(CompanySubscription.company_id == company_id)
    ).scalar_one_or_none()
    if existing_subscription is None:
        plan = db.execute(
            select(SubscriptionPlan).where(SubscriptionPlan.name == "Starter")
        ).scalar_one_or_none()
        if plan is None:
            plan = SubscriptionPlan(
                name="Starter",
                monthly_price=0,
                max_projects=1,
                max_posts_per_month=100,
                max_connectors=2,
            )
            db.add(plan)
            db.flush()
        db.add(
            CompanySubscription(
                company_id=company_id,
                plan_id=plan.id,
                status="active",
                current_period_start=datetime.now(UTC),
                current_period_end=datetime.now(UTC) + timedelta(days=30),
            )
        )
    _ensure_usage_row(db, company_id=company_id)
