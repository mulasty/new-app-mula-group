import hmac
import hashlib
from datetime import UTC, datetime
from uuid import uuid4
import os

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from app.application.services.stripe_checkout_service import verify_stripe_signature
from app.application.services.stripe_webhook_service import process_stripe_event_payload
from app.core.config import settings
from app.domain.models.company import Company
from app.domain.models.company_subscription import CompanySubscription
from app.domain.models.stripe_event import StripeEvent
from app.domain.models.subscription_plan import SubscriptionPlan
from app.infrastructure.db.base import Base

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", os.getenv("DATABASE_URL", ""))


@pytest.fixture(scope="session")
def db_engine():
    if not TEST_DATABASE_URL:
        pytest.skip("DATABASE_URL is required")
    engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        pytest.skip(f"Database unavailable: {exc}")
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db(db_engine):
    Session = sessionmaker(bind=db_engine, autocommit=False, autoflush=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def test_verify_stripe_signature_valid_and_invalid():
    previous = settings.stripe_webhook_secret
    settings.stripe_webhook_secret = "whsec_test"
    payload = b'{"id":"evt_1","type":"invoice.paid"}'
    timestamp = str(int(datetime.now(UTC).timestamp()))
    signed = f"{timestamp}.".encode("utf-8") + payload
    digest = hmac.new(settings.stripe_webhook_secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
    header = f"t={timestamp},v1={digest}"

    verify_stripe_signature(payload_bytes=payload, signature_header=header)

    with pytest.raises(HTTPException):
        verify_stripe_signature(payload_bytes=payload, signature_header=f"t={timestamp},v1=bad")

    settings.stripe_webhook_secret = previous


def test_process_stripe_event_idempotent(db):
    company = Company(id=uuid4(), name="Billing Co", slug=f"billing-co-{uuid4().hex[:8]}")
    plan = SubscriptionPlan(
        id=uuid4(),
        name="Starter",
        monthly_price=0,
        max_projects=1,
        max_posts_per_month=100,
        max_connectors=2,
    )
    db.add(company)
    db.add(plan)
    db.flush()
    subscription = CompanySubscription(company_id=company.id, plan_id=plan.id, status="incomplete")
    db.add(subscription)
    db.commit()

    payload = {
        "id": "evt_test_checkout_completed",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_test_123",
                "customer": "cus_123",
                "subscription": "sub_123",
                "client_reference_id": str(company.id),
                "metadata": {
                    "company_id": str(company.id),
                    "plan_name": "Starter",
                },
            }
        },
    }

    first = process_stripe_event_payload(db, payload)
    db.commit()
    second = process_stripe_event_payload(db, payload)
    db.commit()

    assert first["processed"] is True
    assert second["deduplicated"] is True

    events = db.execute(select(StripeEvent).where(StripeEvent.stripe_event_id == "evt_test_checkout_completed")).scalars().all()
    assert len(events) == 1
