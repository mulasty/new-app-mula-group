"""stripe full subscription lifecycle for v1

Revision ID: 0018_stripe_lifecycle_v1
Revises: 0017_ai_quality_v1
Create Date: 2026-02-16 06:35:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0018_stripe_lifecycle_v1"
down_revision = "0017_ai_quality_v1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("subscription_plans", sa.Column("stripe_price_id", sa.String(length=255), nullable=True))
    op.add_column("subscription_plans", sa.Column("stripe_product_id", sa.String(length=255), nullable=True))
    op.create_index("ix_subscription_plans_stripe_price_id", "subscription_plans", ["stripe_price_id"], unique=False)

    op.add_column("company_subscriptions", sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "company_subscriptions",
        sa.Column("cancel_at_period_end", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("company_subscriptions", sa.Column("grace_period_end", sa.DateTime(timezone=True), nullable=True))
    op.add_column("company_subscriptions", sa.Column("last_invoice_status", sa.String(length=64), nullable=True))
    op.add_column("company_subscriptions", sa.Column("last_payment_error", sa.String(length=1024), nullable=True))

    op.create_table(
        "stripe_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stripe_event_id", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="received"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("stripe_event_id", name="uq_stripe_events_stripe_event_id"),
    )
    op.create_index("ix_stripe_events_stripe_event_id", "stripe_events", ["stripe_event_id"], unique=True)
    op.create_index("ix_stripe_events_status", "stripe_events", ["status"], unique=False)
    op.create_index("ix_stripe_events_received_at", "stripe_events", ["received_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_stripe_events_received_at", table_name="stripe_events")
    op.drop_index("ix_stripe_events_status", table_name="stripe_events")
    op.drop_index("ix_stripe_events_stripe_event_id", table_name="stripe_events")
    op.drop_table("stripe_events")

    op.drop_column("company_subscriptions", "last_payment_error")
    op.drop_column("company_subscriptions", "last_invoice_status")
    op.drop_column("company_subscriptions", "grace_period_end")
    op.drop_column("company_subscriptions", "cancel_at_period_end")
    op.drop_column("company_subscriptions", "current_period_start")

    op.drop_index("ix_subscription_plans_stripe_price_id", table_name="subscription_plans")
    op.drop_column("subscription_plans", "stripe_product_id")
    op.drop_column("subscription_plans", "stripe_price_id")
