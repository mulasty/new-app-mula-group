"""add phase8 platform operating system tables

Revision ID: 0014_phase8_ops_core
Revises: 0013_phase7_growth_ops
Create Date: 2026-02-17 00:35:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "0014_phase8_ops_core"
down_revision = "0013_phase7_growth_ops"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "system_health",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("component", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("latency_ms", sa.Float(), nullable=False, server_default="0"),
        sa.Column("error_rate", sa.Float(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_system_health_component", "system_health", ["component"], unique=False)
    op.create_index("ix_system_health_status", "system_health", ["status"], unique=False)

    op.create_table(
        "tenant_risk_scores",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("risk_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("publish_failure_ratio", sa.Float(), nullable=False, server_default="0"),
        sa.Column("flagged_content_ratio", sa.Float(), nullable=False, server_default="0"),
        sa.Column("abuse_rate", sa.Float(), nullable=False, server_default="0"),
        sa.Column("rate_limit_violations", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("risk_level", sa.String(length=16), nullable=False, server_default="low"),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", name="uq_tenant_risk_scores_company"),
    )
    op.create_index("ix_tenant_risk_scores_company_id", "tenant_risk_scores", ["company_id"], unique=True)

    op.create_table(
        "revenue_metrics",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mrr", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("plan", sa.String(length=64), nullable=False, server_default="Starter"),
        sa.Column("usage_percent", sa.Float(), nullable=False, server_default="0"),
        sa.Column("churn_risk_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("upgrade_probability", sa.Float(), nullable=False, server_default="0"),
        sa.Column("overuse_detected", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", name="uq_revenue_metrics_company"),
    )
    op.create_index("ix_revenue_metrics_company_id", "revenue_metrics", ["company_id"], unique=True)

    op.create_table(
        "platform_incidents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("incident_type", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False, server_default="warning"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="open"),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_platform_incidents_company_id", "platform_incidents", ["company_id"], unique=False)
    op.create_index("ix_platform_incidents_incident_type", "platform_incidents", ["incident_type"], unique=False)
    op.create_index("ix_platform_incidents_status", "platform_incidents", ["status"], unique=False)

    op.create_table(
        "performance_baselines",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("component", sa.String(length=64), nullable=False),
        sa.Column("metric_name", sa.String(length=128), nullable=False),
        sa.Column("avg_value", sa.Float(), nullable=False, server_default="0"),
        sa.Column("p95_value", sa.Float(), nullable=False, server_default="0"),
        sa.Column("sample_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("regression_detected", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_performance_baselines_component", "performance_baselines", ["component"], unique=False)
    op.create_index("ix_performance_baselines_metric_name", "performance_baselines", ["metric_name"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_performance_baselines_metric_name", table_name="performance_baselines")
    op.drop_index("ix_performance_baselines_component", table_name="performance_baselines")
    op.drop_table("performance_baselines")

    op.drop_index("ix_platform_incidents_status", table_name="platform_incidents")
    op.drop_index("ix_platform_incidents_incident_type", table_name="platform_incidents")
    op.drop_index("ix_platform_incidents_company_id", table_name="platform_incidents")
    op.drop_table("platform_incidents")

    op.drop_index("ix_revenue_metrics_company_id", table_name="revenue_metrics")
    op.drop_table("revenue_metrics")

    op.drop_index("ix_tenant_risk_scores_company_id", table_name="tenant_risk_scores")
    op.drop_table("tenant_risk_scores")

    op.drop_index("ix_system_health_status", table_name="system_health")
    op.drop_index("ix_system_health_component", table_name="system_health")
    op.drop_table("system_health")
