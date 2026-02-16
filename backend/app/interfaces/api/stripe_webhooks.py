from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request, status
from sqlalchemy import select

from app.application.services.audit_service import log_audit_event
from app.core.config import settings
from app.domain.models.company_subscription import CompanySubscription
from app.domain.models.subscription_plan import SubscriptionPlan
from app.domain.models.webhook_event import WebhookEvent
from app.infrastructure.db.session import SessionLocal

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _parse_company_id_from_object(obj: dict) -> UUID | None:
    metadata = obj.get("metadata") if isinstance(obj, dict) else None
    company_id_raw = None
    if isinstance(metadata, dict):
        company_id_raw = metadata.get("company_id")
    if not company_id_raw:
        company_id_raw = obj.get("client_reference_id") if isinstance(obj, dict) else None
    if not company_id_raw:
        return None
    try:
        return UUID(str(company_id_raw))
    except ValueError:
        return None


def _resolve_plan(db, event_object: dict) -> SubscriptionPlan | None:
    metadata = event_object.get("metadata") if isinstance(event_object, dict) else None
    plan_name = None
    if isinstance(metadata, dict):
        plan_name = metadata.get("plan_name")
    if plan_name:
        return db.execute(select(SubscriptionPlan).where(SubscriptionPlan.name == str(plan_name))).scalar_one_or_none()
    return db.execute(select(SubscriptionPlan).order_by(SubscriptionPlan.monthly_price.asc())).scalars().first()


@router.post("/stripe", status_code=status.HTTP_200_OK)
async def stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
) -> dict:
    if settings.stripe_webhook_secret and not stripe_signature:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing Stripe signature")

    payload = await request.json()
    with SessionLocal() as db:
        result = process_stripe_event_payload(db, payload)
        db.commit()
    return result


def process_stripe_event_payload(db, payload: dict) -> dict:
    event_type = str(payload.get("type") or "")
    event_data_object = ((payload.get("data") or {}).get("object") or {})
    webhook_event = WebhookEvent(
        provider="stripe",
        event_type=event_type or "unknown",
        external_event_id=str(payload.get("id") or "") or None,
        payload_json=payload,
        status="processing",
    )
    db.add(webhook_event)
    db.flush()

    if event_type == "checkout.session.completed":
        company_id = _parse_company_id_from_object(event_data_object)
        if company_id is None:
            webhook_event.status = "ignored"
            db.add(webhook_event)
            return {"received": True, "ignored": True}

        plan = _resolve_plan(db, event_data_object)
        if plan is None:
            webhook_event.status = "ignored"
            db.add(webhook_event)
            return {"received": True, "ignored": True}

        company_subscription = db.execute(
            select(CompanySubscription).where(CompanySubscription.company_id == company_id)
        ).scalar_one_or_none()
        if company_subscription is None:
            company_subscription = CompanySubscription(company_id=company_id, plan_id=plan.id)
        company_subscription.plan_id = plan.id
        company_subscription.status = "active"
        company_subscription.stripe_customer_id = event_data_object.get("customer")
        company_subscription.stripe_subscription_id = event_data_object.get("subscription")
        company_subscription.current_period_end = datetime.now(UTC) + timedelta(days=30)
        db.add(company_subscription)
        log_audit_event(
            db,
            company_id=company_id,
            action="subscription.changed",
            metadata={"event": event_type, "plan": plan.name},
        )
    elif event_type == "invoice.paid":
        stripe_subscription_id = event_data_object.get("subscription")
        if stripe_subscription_id:
            company_subscription = db.execute(
                select(CompanySubscription).where(
                    CompanySubscription.stripe_subscription_id == str(stripe_subscription_id)
                )
            ).scalar_one_or_none()
            if company_subscription is not None:
                company_subscription.status = "active"
                company_subscription.current_period_end = datetime.now(UTC) + timedelta(days=30)
                db.add(company_subscription)
                log_audit_event(
                    db,
                    company_id=company_subscription.company_id,
                    action="subscription.changed",
                    metadata={"event": event_type, "stripe_subscription_id": str(stripe_subscription_id)},
                )
    elif event_type == "customer.subscription.deleted":
        stripe_subscription_id = event_data_object.get("id")
        if stripe_subscription_id:
            company_subscription = db.execute(
                select(CompanySubscription).where(
                    CompanySubscription.stripe_subscription_id == str(stripe_subscription_id)
                )
            ).scalar_one_or_none()
            if company_subscription is not None:
                company_subscription.status = "canceled"
                db.add(company_subscription)
                log_audit_event(
                    db,
                    company_id=company_subscription.company_id,
                    action="subscription.changed",
                    metadata={"event": event_type, "stripe_subscription_id": str(stripe_subscription_id)},
                )

    webhook_event.status = "processed"
    db.add(webhook_event)
    return {"received": True, "event_id": str(webhook_event.id)}
