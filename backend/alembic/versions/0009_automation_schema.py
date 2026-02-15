"""add phase 6 automation schema

Revision ID: 0009_automation_schema
Revises: 0008_universal_connector
Create Date: 2026-02-15 23:30:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0009_automation_schema"
down_revision = "0008_universal_connector"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "campaigns",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("timezone", sa.String(length=64), nullable=False, server_default="Europe/Warsaw"),
        sa.Column("language", sa.String(length=16), nullable=False, server_default="pl"),
        sa.Column(
            "brand_profile_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("status IN ('draft', 'active', 'paused', 'archived')", name="ck_campaigns_status_values"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_campaigns_company_id", "campaigns", ["company_id"], unique=False)
    op.create_index("ix_campaigns_project_id", "campaigns", ["project_id"], unique=False)

    op.create_table(
        "automation_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("trigger_type", sa.String(length=32), nullable=False),
        sa.Column(
            "trigger_config_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("action_type", sa.String(length=32), nullable=False),
        sa.Column(
            "action_config_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "guardrails_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "trigger_type IN ('cron', 'interval', 'event')",
            name="ck_automation_rules_trigger_values",
        ),
        sa.CheckConstraint(
            "action_type IN ('generate_post', 'schedule_post', 'publish_now', 'sync_metrics')",
            name="ck_automation_rules_action_values",
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_automation_rules_campaign_id", "automation_rules", ["campaign_id"], unique=False)
    op.create_index("ix_automation_rules_company_id", "automation_rules", ["company_id"], unique=False)
    op.create_index("ix_automation_rules_project_id", "automation_rules", ["project_id"], unique=False)

    op.create_table(
        "content_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("template_type", sa.String(length=32), nullable=False, server_default="post_text"),
        sa.Column("prompt_template", sa.Text(), nullable=False),
        sa.Column(
            "output_schema_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "default_values_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "template_type IN ('post_text', 'carousel_plan', 'video_script')",
            name="ck_content_templates_type_values",
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_content_templates_company_id", "content_templates", ["company_id"], unique=False)
    op.create_index("ix_content_templates_project_id", "content_templates", ["project_id"], unique=False)

    op.create_table(
        "content_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("template_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="ai"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "status IN ('draft', 'needs_review', 'approved', 'rejected', 'scheduled', 'published', 'failed')",
            name="ck_content_items_status_values",
        ),
        sa.CheckConstraint("source IN ('ai', 'manual')", name="ck_content_items_source_values"),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["template_id"], ["content_templates.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_content_items_campaign_id", "content_items", ["campaign_id"], unique=False)
    op.create_index("ix_content_items_company_id", "content_items", ["company_id"], unique=False)
    op.create_index("ix_content_items_project_id", "content_items", ["project_id"], unique=False)
    op.create_index("ix_content_items_status_created_at", "content_items", ["company_id", "project_id", "status", "created_at"], unique=False)
    op.create_index("ix_content_items_template_id", "content_items", ["template_id"], unique=False)

    op.create_table(
        "approvals",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("content_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reviewed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("status IN ('pending', 'approved', 'rejected')", name="ck_approvals_status_values"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["content_item_id"], ["content_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_approvals_company_id", "approvals", ["company_id"], unique=False)
    op.create_index("ix_approvals_content_item_id", "approvals", ["content_item_id"], unique=False)
    op.create_index("ix_approvals_project_id", "approvals", ["project_id"], unique=False)

    op.create_table(
        "automation_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rule_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "stats_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'success', 'partial', 'failed')",
            name="ck_automation_runs_status_values",
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["rule_id"], ["automation_rules.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_automation_runs_company_id", "automation_runs", ["company_id"], unique=False)
    op.create_index("ix_automation_runs_project_id", "automation_runs", ["project_id"], unique=False)
    op.create_index("ix_automation_runs_rule_id", "automation_runs", ["rule_id"], unique=False)

    op.create_table(
        "automation_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="ok"),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("status IN ('ok', 'error')", name="ck_automation_events_status_values"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["automation_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_automation_events_company_id", "automation_events", ["company_id"], unique=False)
    op.create_index("ix_automation_events_project_id", "automation_events", ["project_id"], unique=False)
    op.create_index("ix_automation_events_run_id", "automation_events", ["run_id"], unique=False)
    op.create_index(
        "ix_automation_events_company_project_created_at",
        "automation_events",
        ["company_id", "project_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_automation_events_company_project_created_at", table_name="automation_events")
    op.drop_index("ix_automation_events_run_id", table_name="automation_events")
    op.drop_index("ix_automation_events_project_id", table_name="automation_events")
    op.drop_index("ix_automation_events_company_id", table_name="automation_events")
    op.drop_table("automation_events")

    op.drop_index("ix_automation_runs_rule_id", table_name="automation_runs")
    op.drop_index("ix_automation_runs_project_id", table_name="automation_runs")
    op.drop_index("ix_automation_runs_company_id", table_name="automation_runs")
    op.drop_table("automation_runs")

    op.drop_index("ix_approvals_project_id", table_name="approvals")
    op.drop_index("ix_approvals_content_item_id", table_name="approvals")
    op.drop_index("ix_approvals_company_id", table_name="approvals")
    op.drop_table("approvals")

    op.drop_index("ix_content_items_template_id", table_name="content_items")
    op.drop_index("ix_content_items_status_created_at", table_name="content_items")
    op.drop_index("ix_content_items_project_id", table_name="content_items")
    op.drop_index("ix_content_items_company_id", table_name="content_items")
    op.drop_index("ix_content_items_campaign_id", table_name="content_items")
    op.drop_table("content_items")

    op.drop_index("ix_content_templates_project_id", table_name="content_templates")
    op.drop_index("ix_content_templates_company_id", table_name="content_templates")
    op.drop_table("content_templates")

    op.drop_index("ix_automation_rules_project_id", table_name="automation_rules")
    op.drop_index("ix_automation_rules_company_id", table_name="automation_rules")
    op.drop_index("ix_automation_rules_campaign_id", table_name="automation_rules")
    op.drop_table("automation_rules")

    op.drop_index("ix_campaigns_project_id", table_name="campaigns")
    op.drop_index("ix_campaigns_company_id", table_name="campaigns")
    op.drop_table("campaigns")
