from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import httpx
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.domain.models.company import Company
from app.domain.models.company_subscription import CompanySubscription
from app.domain.models.subscription_plan import SubscriptionPlan


@dataclass(frozen=True)
class CheckoutSessionResult:
    checkout_url: str
    session_id: str


def _plan_price_id(plan_name: str) -> str | None:
    mapping = {
        "starter": settings.stripe_price_id_starter,
        "pro": settings.stripe_price_id_pro,
        "enterprise": settings.stripe_price_id_enterprise,
    }
    return mapping.get(plan_name.lower())


def _resolve_plan(db: Session, plan_name: str) -> SubscriptionPlan:
    plan = db.execute(select(SubscriptionPlan).where(SubscriptionPlan.name == plan_name)).scalar_one_or_none()
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")
    return plan


def create_checkout_session(
    db: Session,
    *,
    company_id: UUID,
    plan_name: str,
    success_url: str | None = None,
    cancel_url: str | None = None,
) -> CheckoutSessionResult:
    if not settings.stripe_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Stripe is not configured",
        )

    company = db.execute(select(Company).where(Company.id == company_id)).scalar_one_or_none()
    if company is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")

    plan = _resolve_plan(db, plan_name)
    price_id = _plan_price_id(plan.name)
    if not price_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Price ID is not configured for plan '{plan.name}'",
        )

    current_subscription = db.execute(
        select(CompanySubscription).where(CompanySubscription.company_id == company_id)
    ).scalar_one_or_none()

    payload = {
        "mode": "subscription",
        "line_items[0][price]": price_id,
        "line_items[0][quantity]": "1",
        "success_url": success_url or settings.stripe_checkout_success_url,
        "cancel_url": cancel_url or settings.stripe_checkout_cancel_url,
        "client_reference_id": str(company_id),
        "metadata[company_id]": str(company_id),
        "metadata[plan_name]": plan.name,
    }
    if current_subscription and current_subscription.stripe_customer_id:
        payload["customer"] = current_subscription.stripe_customer_id

    response = httpx.post(
        "https://api.stripe.com/v1/checkout/sessions",
        data=payload,
        headers={"Authorization": f"Bearer {settings.stripe_api_key}"},
        timeout=20.0,
    )
    if response.status_code >= 400:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Stripe checkout error: {response.text[:200]}",
        )
    body = response.json()
    checkout_url = str(body.get("url") or "")
    session_id = str(body.get("id") or "")
    if not checkout_url or not session_id:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Stripe checkout response invalid")
    return CheckoutSessionResult(checkout_url=checkout_url, session_id=session_id)

