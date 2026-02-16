from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.services.audit_service import log_audit_event
from app.core.config import settings
from app.domain.models.billing_event import BillingEvent
from app.domain.models.company_subscription import CompanySubscription
from app.domain.models.stripe_event import StripeEvent
from app.domain.models.subscription_plan import SubscriptionPlan


def _from_unix(value) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=UTC)
    except Exception:
        return None


def _get_or_create_subscription(db: Session, *, company_id: UUID, default_plan: SubscriptionPlan | None = None) -> CompanySubscription:
    subscription = db.execute(select(CompanySubscription).where(CompanySubscription.company_id == company_id)).scalar_one_or_none()
    if subscription is not None:
        return subscription

    plan = default_plan
    if plan is None:
        plan = db.execute(select(SubscriptionPlan).where(SubscriptionPlan.name == "Starter")).scalar_one_or_none()
    if plan is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Starter plan missing")

    subscription = CompanySubscription(
        company_id=company_id,
        plan_id=plan.id,
        status="incomplete",
        current_period_start=datetime.now(UTC),
        current_period_end=datetime.now(UTC) + timedelta(days=30),
    )
    db.add(subscription)
    db.flush()
    return subscription


def _plan_from_event(db: Session, event_object: dict) -> SubscriptionPlan | None:
    metadata = event_object.get("metadata") if isinstance(event_object, dict) else None
    plan_id_raw = metadata.get("plan_id") if isinstance(metadata, dict) else None
    plan_name = metadata.get("plan_name") if isinstance(metadata, dict) else None

    if plan_id_raw:
        try:
            plan_id = UUID(str(plan_id_raw))
            plan = db.execute(select(SubscriptionPlan).where(SubscriptionPlan.id == plan_id)).scalar_one_or_none()
            if plan is not None:
                return plan
        except ValueError:
            pass

    if plan_name:
        plan = db.execute(select(SubscriptionPlan).where(SubscriptionPlan.name == str(plan_name))).scalar_one_or_none()
        if plan is not None:
            return plan

    return db.execute(select(SubscriptionPlan).order_by(SubscriptionPlan.monthly_price.asc())).scalars().first()


def _extract_company_id(event_object: dict) -> UUID | None:
    metadata = event_object.get("metadata") if isinstance(event_object, dict) else None
    raw = None
    if isinstance(metadata, dict):
        raw = metadata.get("company_id")
    raw = raw or event_object.get("client_reference_id")
    if not raw:
        customer_details = event_object.get("customer_details") if isinstance(event_object, dict) else None
        if isinstance(customer_details, dict):
            raw = (customer_details.get("metadata") or {}).get("company_id")
    if not raw:
        return None
    try:
        return UUID(str(raw))
    except ValueError:
        return None


def _record_billing_event(db: Session, *, company_id: UUID, event_type: str, message: str, metadata: dict | None = None) -> None:
    db.add(BillingEvent(company_id=company_id, event_type=event_type, message=message, metadata_json=metadata or {}))


def _set_subscription_from_stripe_object(
    db: Session,
    *,
    subscription: CompanySubscription,
    stripe_subscription: dict,
) -> None:
    status_value = str(stripe_subscription.get("status") or subscription.status or "incomplete")
    subscription.status = status_value
    subscription.stripe_subscription_id = str(stripe_subscription.get("id") or subscription.stripe_subscription_id or "") or None
    subscription.stripe_customer_id = str(stripe_subscription.get("customer") or subscription.stripe_customer_id or "") or None
    subscription.current_period_start = _from_unix(stripe_subscription.get("current_period_start"))
    subscription.current_period_end = _from_unix(stripe_subscription.get("current_period_end"))
    subscription.cancel_at_period_end = bool(stripe_subscription.get("cancel_at_period_end", False))
    db.add(subscription)


def process_stripe_event_payload(db: Session, payload: dict) -> dict:
    event_id = str(payload.get("id") or "").strip()
    event_type = str(payload.get("type") or "unknown")
    event_object = ((payload.get("data") or {}).get("object") or {})

    if not event_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing Stripe event id")

    existing = db.execute(select(StripeEvent).where(StripeEvent.stripe_event_id == event_id)).scalar_one_or_none()
    if existing is not None and existing.status == "processed":
        return {"received": True, "deduplicated": True, "stripe_event_id": event_id}

    stripe_event = existing or StripeEvent(stripe_event_id=event_id, event_type=event_type, status="processing")
    stripe_event.event_type = event_type
    stripe_event.status = "processing"
    stripe_event.error = None
    db.add(stripe_event)
    db.flush()

    try:
        if event_type == "checkout.session.completed":
            company_id = _extract_company_id(event_object)
            if company_id is not None:
                plan = _plan_from_event(db, event_object)
                subscription = _get_or_create_subscription(db, company_id=company_id, default_plan=plan)
                if plan is not None:
                    subscription.plan_id = plan.id
                subscription.status = "active"
                subscription.stripe_customer_id = str(event_object.get("customer") or subscription.stripe_customer_id or "") or None
                subscription.stripe_subscription_id = str(event_object.get("subscription") or subscription.stripe_subscription_id or "") or None
                subscription.last_payment_error = None
                db.add(subscription)
                _record_billing_event(
                    db,
                    company_id=company_id,
                    event_type=event_type,
                    message="Checkout session completed",
                    metadata={"stripe_event_id": event_id},
                )
                log_audit_event(db, company_id=company_id, action="billing.webhook_applied", metadata={"event_type": event_type, "stripe_event_id": event_id})

        elif event_type in {"customer.subscription.created", "customer.subscription.updated", "customer.subscription.deleted"}:
            stripe_subscription_id = str(event_object.get("id") or "")
            if stripe_subscription_id:
                subscription = db.execute(
                    select(CompanySubscription).where(CompanySubscription.stripe_subscription_id == stripe_subscription_id)
                ).scalar_one_or_none()
                if subscription is not None:
                    _set_subscription_from_stripe_object(db, subscription=subscription, stripe_subscription=event_object)
                    if event_type == "customer.subscription.deleted":
                        subscription.status = "canceled"
                        db.add(subscription)
                    _record_billing_event(
                        db,
                        company_id=subscription.company_id,
                        event_type=event_type,
                        message=f"Subscription event: {event_type}",
                        metadata={"stripe_subscription_id": stripe_subscription_id, "stripe_event_id": event_id},
                    )
                    log_audit_event(db, company_id=subscription.company_id, action="billing.webhook_applied", metadata={"event_type": event_type, "stripe_event_id": event_id})

        elif event_type in {"invoice.paid", "invoice.payment_failed", "invoice.finalized"}:
            stripe_subscription_id = str(event_object.get("subscription") or "")
            if stripe_subscription_id:
                subscription = db.execute(
                    select(CompanySubscription).where(CompanySubscription.stripe_subscription_id == stripe_subscription_id)
                ).scalar_one_or_none()
                if subscription is not None:
                    invoice_status = str(event_object.get("status") or "")
                    subscription.last_invoice_status = invoice_status or subscription.last_invoice_status
                    if event_type == "invoice.paid":
                        subscription.status = "active"
                        subscription.last_payment_error = None
                        subscription.grace_period_end = None
                    elif event_type == "invoice.payment_failed":
                        subscription.status = "past_due"
                        subscription.last_payment_error = str((event_object.get("last_finalization_error") or {}).get("message") or "payment_failed")
                        subscription.grace_period_end = datetime.now(UTC) + timedelta(days=max(1, settings.billing_grace_period_days))
                        log_audit_event(
                            db,
                            company_id=subscription.company_id,
                            action="billing.payment_failed",
                            metadata={"stripe_event_id": event_id, "grace_period_end": subscription.grace_period_end.isoformat() if subscription.grace_period_end else None},
                        )
                        log_audit_event(
                            db,
                            company_id=subscription.company_id,
                            action="billing.grace_activated",
                            metadata={"stripe_event_id": event_id},
                        )
                    db.add(subscription)
                    _record_billing_event(
                        db,
                        company_id=subscription.company_id,
                        event_type=event_type,
                        message=f"Invoice event: {event_type}",
                        metadata={"stripe_subscription_id": stripe_subscription_id, "invoice_status": invoice_status, "stripe_event_id": event_id},
                    )
                    log_audit_event(db, company_id=subscription.company_id, action="billing.webhook_applied", metadata={"event_type": event_type, "stripe_event_id": event_id})

        elif event_type in {"payment_intent.succeeded", "payment_intent.payment_failed"}:
            metadata = event_object.get("metadata") or {}
            subscription_id = str(metadata.get("subscription_id") or "")
            subscription = None
            if subscription_id:
                subscription = db.execute(
                    select(CompanySubscription).where(CompanySubscription.stripe_subscription_id == subscription_id)
                ).scalar_one_or_none()
            if subscription is not None:
                if event_type == "payment_intent.payment_failed":
                    subscription.status = "past_due"
                    subscription.last_payment_error = str((event_object.get("last_payment_error") or {}).get("message") or "payment_failed")
                    subscription.grace_period_end = datetime.now(UTC) + timedelta(days=max(1, settings.billing_grace_period_days))
                    log_audit_event(
                        db,
                        company_id=subscription.company_id,
                        action="billing.payment_failed",
                        metadata={"stripe_event_id": event_id, "grace_period_end": subscription.grace_period_end.isoformat() if subscription.grace_period_end else None},
                    )
                    log_audit_event(
                        db,
                        company_id=subscription.company_id,
                        action="billing.grace_activated",
                        metadata={"stripe_event_id": event_id},
                    )
                elif event_type == "payment_intent.succeeded":
                    subscription.last_payment_error = None
                    if subscription.status in {"past_due", "unpaid", "incomplete"}:
                        subscription.status = "active"
                    subscription.grace_period_end = None
                db.add(subscription)
                _record_billing_event(
                    db,
                    company_id=subscription.company_id,
                    event_type=event_type,
                    message=f"Payment intent event: {event_type}",
                    metadata={"stripe_event_id": event_id},
                )
                log_audit_event(db, company_id=subscription.company_id, action="billing.webhook_applied", metadata={"event_type": event_type, "stripe_event_id": event_id})

        stripe_event.status = "processed"
        stripe_event.processed_at = datetime.now(UTC)
        db.add(stripe_event)
        return {"received": True, "processed": True, "stripe_event_id": event_id}

    except Exception as exc:
        stripe_event.status = "error"
        stripe_event.error = str(exc)[:4000]
        stripe_event.processed_at = datetime.now(UTC)
        db.add(stripe_event)
        raise
