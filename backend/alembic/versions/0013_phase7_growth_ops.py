"""add phase7 feature flags, webhook events and ai quality policy

Revision ID: 0013_phase7_growth_ops
Revises: 0012_wave3_enterprise_billing
Create Date: 2026-02-17 12:10:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "0013_phase7_growth_ops"
down_revision = "0012_wave3_enterprise_billing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "feature_flags",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("enabled_globally", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "enabled_per_tenant",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key", name="uq_feature_flags_key"),
    )
    op.create_index("ix_feature_flags_key", "feature_flags", ["key"], unique=True)

    op.create_table(
        "webhook_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("external_event_id", sa.String(length=255), nullable=True),
        sa.Column(
            "payload_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="received"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_webhook_events_provider", "webhook_events", ["provider"], unique=False)
    op.create_index("ix_webhook_events_external_event_id", "webhook_events", ["external_event_id"], unique=False)

    op.create_table(
        "ai_quality_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "policy_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "project_id", name="uq_ai_quality_company_project"),
    )
    op.create_index("ix_ai_quality_policies_company_id", "ai_quality_policies", ["company_id"], unique=False)
    op.create_index("ix_ai_quality_policies_project_id", "ai_quality_policies", ["project_id"], unique=False)

    op.execute(
        """
        INSERT INTO feature_flags (id, key, enabled_globally, enabled_per_tenant, description)
        VALUES
            ('20000000-0000-4000-8000-000000000001', 'beta_public_pricing', false, '{}'::jsonb, 'Public pricing and checkout flow'),
            ('20000000-0000-4000-8000-000000000002', 'beta_admin_panel', false, '{}'::jsonb, 'Operator dashboard and support tools'),
            ('20000000-0000-4000-8000-000000000003', 'beta_ai_quality', false, '{}'::jsonb, 'AI quality and safety enforcement')
        ON CONFLICT (key) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index("ix_ai_quality_policies_project_id", table_name="ai_quality_policies")
    op.drop_index("ix_ai_quality_policies_company_id", table_name="ai_quality_policies")
    op.drop_table("ai_quality_policies")

    op.drop_index("ix_webhook_events_external_event_id", table_name="webhook_events")
    op.drop_index("ix_webhook_events_provider", table_name="webhook_events")
    op.drop_table("webhook_events")

    op.drop_index("ix_feature_flags_key", table_name="feature_flags")
    op.drop_table("feature_flags")
