"""add wave3 enterprise billing and audit tables

Revision ID: 0012_wave3_enterprise_billing
Revises: 0011_wave2_scaling_observability
Create Date: 2026-02-16 23:05:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "0012_wave3_enterprise_billing"
down_revision = "0011_wave2_scaling_observability"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "subscription_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("monthly_price", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("max_projects", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("max_posts_per_month", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("max_connectors", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_subscription_plans_name"),
    )

    op.create_table(
        "company_subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stripe_customer_id", sa.String(length=255), nullable=True),
        sa.Column("stripe_subscription_id", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["plan_id"], ["subscription_plans.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", name="uq_company_subscriptions_company_id"),
    )
    op.create_index("ix_company_subscriptions_company_id", "company_subscriptions", ["company_id"], unique=True)
    op.create_index("ix_company_subscriptions_plan_id", "company_subscriptions", ["plan_id"], unique=False)
    op.create_index(
        "ix_company_subscriptions_stripe_subscription_id",
        "company_subscriptions",
        ["stripe_subscription_id"],
        unique=False,
    )

    op.create_table(
        "company_usages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("posts_used_current_period", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("period_started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", name="uq_company_usages_company_id"),
    )
    op.create_index("ix_company_usages_company_id", "company_usages", ["company_id"], unique=True)

    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_logs_company_id", "audit_logs", ["company_id"], unique=False)
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"], unique=False)

    op.execute(
        """
        INSERT INTO subscription_plans (id, name, monthly_price, max_projects, max_posts_per_month, max_connectors)
        VALUES
            ('10000000-0000-4000-8000-000000000001', 'Starter', 0.00, 1, 100, 2),
            ('10000000-0000-4000-8000-000000000002', 'Pro', 49.00, 5, 1000, 10),
            ('10000000-0000-4000-8000-000000000003', 'Enterprise', 199.00, 100, 100000, 100)
        ON CONFLICT (name) DO NOTHING
        """
    )

    op.execute(
        """
        INSERT INTO company_subscriptions (id, company_id, plan_id, status, current_period_end)
        SELECT c.id, c.id, sp.id, 'active', now() + interval '30 days'
        FROM companies c
        CROSS JOIN LATERAL (
            SELECT id FROM subscription_plans WHERE name = 'Starter' LIMIT 1
        ) sp
        LEFT JOIN company_subscriptions cs ON cs.company_id = c.id
        WHERE cs.id IS NULL
        """
    )

    op.execute(
        """
        INSERT INTO company_usages (id, company_id, posts_used_current_period, period_started_at, updated_at)
        SELECT c.id, c.id, 0, now(), now()
        FROM companies c
        LEFT JOIN company_usages cu ON cu.company_id = c.id
        WHERE cu.id IS NULL
        """
    )


def downgrade() -> None:
    op.drop_index("ix_audit_logs_created_at", table_name="audit_logs")
    op.drop_index("ix_audit_logs_company_id", table_name="audit_logs")
    op.drop_table("audit_logs")

    op.drop_index("ix_company_usages_company_id", table_name="company_usages")
    op.drop_table("company_usages")

    op.drop_index("ix_company_subscriptions_stripe_subscription_id", table_name="company_subscriptions")
    op.drop_index("ix_company_subscriptions_plan_id", table_name="company_subscriptions")
    op.drop_index("ix_company_subscriptions_company_id", table_name="company_subscriptions")
    op.drop_table("company_subscriptions")

    op.drop_table("subscription_plans")
