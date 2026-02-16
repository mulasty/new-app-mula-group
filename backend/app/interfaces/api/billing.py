from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.services.audit_service import log_audit_event
from app.application.services.billing_service import bootstrap_company_billing
from app.application.services.feature_flag_service import is_feature_enabled
from app.application.services.stripe_checkout_service import create_checkout_session
from app.domain.models.company_subscription import CompanySubscription
from app.domain.models.company_usage import CompanyUsage
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


def _serialize_plan(plan: SubscriptionPlan) -> dict:
    return {
        "id": str(plan.id),
        "name": plan.name,
        "monthly_price": float(Decimal(plan.monthly_price)),
        "max_projects": plan.max_projects,
        "max_posts_per_month": plan.max_posts_per_month,
        "max_connectors": plan.max_connectors,
    }


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
            "posts_used_current_period": int(usage.posts_used_current_period if usage else 0),
        },
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
