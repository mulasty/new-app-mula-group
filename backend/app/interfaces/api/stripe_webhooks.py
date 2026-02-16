from fastapi import APIRouter, Header, Request, status

from app.application.services.stripe_checkout_service import parse_stripe_webhook_payload, verify_stripe_signature
from app.application.services.stripe_webhook_service import process_stripe_event_payload
from app.domain.models.webhook_event import WebhookEvent
from app.infrastructure.db.session import SessionLocal

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/stripe", status_code=status.HTTP_200_OK)
async def stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
) -> dict:
    payload_bytes = await request.body()
    verify_stripe_signature(payload_bytes=payload_bytes, signature_header=stripe_signature)
    payload = parse_stripe_webhook_payload(payload_bytes)

    with SessionLocal() as db:
        db.add(
            WebhookEvent(
                provider="stripe",
                event_type=str(payload.get("type") or "unknown"),
                external_event_id=str(payload.get("id") or "") or None,
                payload_json=payload,
                status="received",
            )
        )
        result = process_stripe_event_payload(db, payload)
        db.commit()
    return result
