from __future__ import annotations

import hmac
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

import httpx
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.domain.models.company import Company
from app.domain.models.company_subscription import CompanySubscription
from app.domain.models.subscription_plan import SubscriptionPlan

STRIPE_API_BASE = "https://api.stripe.com/v1"


@dataclass(frozen=True)
class CheckoutSessionResult:
    checkout_url: str
    session_id: str


@dataclass(frozen=True)
class PortalSessionResult:
    portal_url: str


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {settings.stripe_api_key}"}


def _require_stripe() -> None:
    if not settings.stripe_api_key:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Stripe is not configured")


def _resolve_plan_by_name(db: Session, plan_name: str) -> SubscriptionPlan:
    plan = db.execute(select(SubscriptionPlan).where(SubscriptionPlan.name == plan_name)).scalar_one_or_none()
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")
    return plan


def _resolve_plan_by_id(db: Session, plan_id: UUID) -> SubscriptionPlan:
    plan = db.execute(select(SubscriptionPlan).where(SubscriptionPlan.id == plan_id)).scalar_one_or_none()
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")
    return plan


def _ensure_customer(db: Session, *, company_id: UUID, company_name: str | None) -> CompanySubscription:
    subscription = db.execute(select(CompanySubscription).where(CompanySubscription.company_id == company_id)).scalar_one_or_none()
    if subscription is None:
        starter = db.execute(select(SubscriptionPlan).where(SubscriptionPlan.name == "Starter")).scalar_one_or_none()
        if starter is None:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Starter plan missing")
        subscription = CompanySubscription(company_id=company_id, plan_id=starter.id, status="incomplete")
        db.add(subscription)
        db.flush()

    if subscription.stripe_customer_id:
        return subscription

    payload = {
        "name": company_name or f"Tenant {company_id}",
        "metadata[company_id]": str(company_id),
    }
    with httpx.Client(timeout=20.0) as client:
        response = client.post(f"{STRIPE_API_BASE}/customers", headers=_headers(), data=payload)
    if response.status_code >= 400:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Stripe customer error: {response.text[:200]}")
    body = response.json()
    customer_id = str(body.get("id") or "")
    if not customer_id:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Stripe customer response invalid")

    subscription.stripe_customer_id = customer_id
    db.add(subscription)
    db.flush()
    return subscription


def create_checkout_session(
    db: Session,
    *,
    company_id: UUID,
    plan_name: str,
    success_url: str | None = None,
    cancel_url: str | None = None,
) -> CheckoutSessionResult:
    plan = _resolve_plan_by_name(db, plan_name)
    return create_checkout_session_by_plan_id(
        db,
        company_id=company_id,
        plan_id=plan.id,
        success_url=success_url,
        cancel_url=cancel_url,
    )


def create_checkout_session_by_plan_id(
    db: Session,
    *,
    company_id: UUID,
    plan_id: UUID,
    success_url: str | None = None,
    cancel_url: str | None = None,
) -> CheckoutSessionResult:
    _require_stripe()
    plan = _resolve_plan_by_id(db, plan_id)
    if not plan.stripe_price_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Plan '{plan.name}' has no Stripe price mapping")

    company = db.execute(select(Company).where(Company.id == company_id)).scalar_one_or_none()
    if company is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")

    subscription = _ensure_customer(db, company_id=company_id, company_name=company.name)

    payload = {
        "mode": "subscription",
        "line_items[0][price]": plan.stripe_price_id,
        "line_items[0][quantity]": "1",
        "success_url": success_url or settings.stripe_checkout_success_url,
        "cancel_url": cancel_url or settings.stripe_checkout_cancel_url,
        "customer": subscription.stripe_customer_id,
        "client_reference_id": str(company_id),
        "metadata[company_id]": str(company_id),
        "metadata[plan_id]": str(plan.id),
        "metadata[plan_name]": plan.name,
    }

    with httpx.Client(timeout=20.0) as client:
        response = client.post(f"{STRIPE_API_BASE}/checkout/sessions", headers=_headers(), data=payload)
    if response.status_code >= 400:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Stripe checkout error: {response.text[:200]}")
    body = response.json()
    checkout_url = str(body.get("url") or "")
    session_id = str(body.get("id") or "")
    if not checkout_url or not session_id:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Stripe checkout response invalid")
    return CheckoutSessionResult(checkout_url=checkout_url, session_id=session_id)


def create_billing_portal_session(
    db: Session,
    *,
    company_id: UUID,
    return_url: str | None,
) -> PortalSessionResult:
    _require_stripe()
    company = db.execute(select(Company).where(Company.id == company_id)).scalar_one_or_none()
    if company is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")

    subscription = _ensure_customer(db, company_id=company_id, company_name=company.name)
    payload = {
        "customer": subscription.stripe_customer_id,
        "return_url": return_url or settings.stripe_billing_portal_return_url,
    }
    with httpx.Client(timeout=20.0) as client:
        response = client.post(f"{STRIPE_API_BASE}/billing_portal/sessions", headers=_headers(), data=payload)
    if response.status_code >= 400:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Stripe portal error: {response.text[:200]}")
    body = response.json()
    url = str(body.get("url") or "")
    if not url:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Stripe portal response invalid")
    return PortalSessionResult(portal_url=url)


def change_subscription_plan(
    db: Session,
    *,
    company_id: UUID,
    plan_id: UUID,
) -> dict:
    _require_stripe()
    target_plan = _resolve_plan_by_id(db, plan_id)
    if not target_plan.stripe_price_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Target plan has no Stripe price mapping")

    subscription = db.execute(select(CompanySubscription).where(CompanySubscription.company_id == company_id)).scalar_one_or_none()
    if subscription is None or not subscription.stripe_subscription_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="No active Stripe subscription")

    with httpx.Client(timeout=20.0) as client:
        existing = client.get(
            f"{STRIPE_API_BASE}/subscriptions/{subscription.stripe_subscription_id}",
            headers=_headers(),
            params={"expand[]": "items.data.price"},
        )
    if existing.status_code >= 400:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Stripe subscription fetch error: {existing.text[:200]}")
    existing_body = existing.json()
    items = ((existing_body.get("items") or {}).get("data") or [])
    if not items:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Stripe subscription items missing")
    item_id = str(items[0].get("id") or "")
    if not item_id:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Stripe subscription item id missing")

    proration_behavior = settings.billing_proration_mode
    payload = {
        "items[0][id]": item_id,
        "items[0][price]": target_plan.stripe_price_id,
        "proration_behavior": proration_behavior,
    }
    with httpx.Client(timeout=20.0) as client:
        update = client.post(
            f"{STRIPE_API_BASE}/subscriptions/{subscription.stripe_subscription_id}",
            headers=_headers(),
            data=payload,
        )
    if update.status_code >= 400:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Stripe subscription update error: {update.text[:200]}")

    # optimistic local update (authoritative state still from webhooks)
    subscription.plan_id = target_plan.id
    subscription.status = "active"
    subscription.last_payment_error = None
    subscription.last_invoice_status = "pending_webhook_confirmation"
    db.add(subscription)
    db.flush()

    return {
        "updated": True,
        "plan": {
            "id": str(target_plan.id),
            "name": target_plan.name,
            "stripe_price_id": target_plan.stripe_price_id,
        },
        "proration_behavior": proration_behavior,
    }


def verify_stripe_signature(*, payload_bytes: bytes, signature_header: str | None) -> None:
    if not settings.stripe_webhook_secret:
        return
    if not signature_header:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing Stripe signature")

    parts = {}
    for chunk in signature_header.split(","):
        if "=" not in chunk:
            continue
        key, value = chunk.split("=", 1)
        parts[key.strip()] = value.strip()

    timestamp = parts.get("t")
    signature = parts.get("v1")
    if not timestamp or not signature:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Stripe signature header")

    try:
        signed_at = int(timestamp)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Stripe signature timestamp") from exc

    age = abs(int(datetime.now(UTC).timestamp()) - signed_at)
    if age > max(1, settings.stripe_webhook_tolerance_seconds):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Expired Stripe signature")

    signed_payload = f"{timestamp}.".encode("utf-8") + payload_bytes
    expected = hmac.new(
        settings.stripe_webhook_secret.encode("utf-8"),
        signed_payload,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Stripe signature")


def parse_stripe_webhook_payload(payload_bytes: bytes) -> dict:
    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Stripe payload") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Stripe payload")
    return payload
