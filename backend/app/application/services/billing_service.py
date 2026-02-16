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

PLAN_LIMIT_ERROR = {
    "error_code": "PLAN_LIMIT_EXCEEDED",
    "message": "Upgrade your plan.",
}


def _resolve_plan_context(db: Session, *, company_id: UUID) -> tuple[CompanySubscription | None, SubscriptionPlan | None]:
    company_subscription = db.execute(
        select(CompanySubscription).where(CompanySubscription.company_id == company_id)
    ).scalar_one_or_none()
    if company_subscription is None:
        return None, None
    plan = db.execute(select(SubscriptionPlan).where(SubscriptionPlan.id == company_subscription.plan_id)).scalar_one_or_none()
    return company_subscription, plan


def _ensure_usage_row(db: Session, *, company_id: UUID) -> CompanyUsage:
    usage = db.execute(select(CompanyUsage).where(CompanyUsage.company_id == company_id)).scalar_one_or_none()
    if usage is not None:
        return usage
    usage = CompanyUsage(company_id=company_id, posts_used_current_period=0)
    db.add(usage)
    db.flush()
    return usage


def enforce_project_limit(db: Session, *, company_id: UUID) -> None:
    _, plan = _resolve_plan_context(db, company_id=company_id)
    if plan is None:
        return
    current_projects = db.execute(
        select(func.count(Project.id)).where(Project.company_id == company_id)
    ).scalar_one()
    if int(current_projects or 0) >= int(plan.max_projects):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=PLAN_LIMIT_ERROR)


def enforce_connector_limit(db: Session, *, company_id: UUID) -> None:
    _, plan = _resolve_plan_context(db, company_id=company_id)
    if plan is None:
        return
    current_connectors = db.execute(
        select(func.count(Channel.id)).where(Channel.company_id == company_id)
    ).scalar_one()
    if int(current_connectors or 0) >= int(plan.max_connectors):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=PLAN_LIMIT_ERROR)


def enforce_post_limit(db: Session, *, company_id: UUID) -> None:
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
                current_period_end=datetime.now(UTC) + timedelta(days=30),
            )
        )
    _ensure_usage_row(db, company_id=company_id)
