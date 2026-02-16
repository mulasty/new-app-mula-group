"""add brand profiles and post quality reporting

Revision ID: 0017_ai_quality_v1
Revises: 0016_connector_hardening_b
Create Date: 2026-02-16 05:20:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0017_ai_quality_v1"
down_revision = "0016_connector_hardening_b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_posts_status_values", "posts", type_="check")
    op.create_check_constraint(
        "ck_posts_status_values",
        "posts",
        "status IN ('draft', 'needs_approval', 'scheduled', 'publishing', 'published', 'published_partial', 'failed')",
    )

    op.create_table(
        "brand_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("brand_name", sa.String(length=255), nullable=False),
        sa.Column("language", sa.String(length=16), nullable=False, server_default="pl"),
        sa.Column("tone", sa.String(length=32), nullable=False, server_default="professional"),
        sa.Column("target_audience", sa.Text(), nullable=True),
        sa.Column("do_list", postgresql.ARRAY(sa.String(length=255)), nullable=False, server_default="{}"),
        sa.Column("dont_list", postgresql.ARRAY(sa.String(length=255)), nullable=False, server_default="{}"),
        sa.Column("forbidden_claims", postgresql.ARRAY(sa.String(length=255)), nullable=False, server_default="{}"),
        sa.Column("preferred_hashtags", postgresql.ARRAY(sa.String(length=128)), nullable=False, server_default="{}"),
        sa.Column("compliance_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "project_id", name="uq_brand_profiles_company_project"),
    )
    op.create_index("ix_brand_profiles_company_id", "brand_profiles", ["company_id"], unique=False)
    op.create_index("ix_brand_profiles_project_id", "brand_profiles", ["project_id"], unique=False)
    op.create_index(
        "uq_brand_profiles_company_default",
        "brand_profiles",
        ["company_id"],
        unique=True,
        postgresql_where=sa.text("project_id IS NULL"),
    )

    op.create_table(
        "post_quality_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("post_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("risk_level", sa.String(length=16), nullable=False),
        sa.Column("issues", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["post_id"], ["posts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_post_quality_reports_post_id", "post_quality_reports", ["post_id"], unique=False)
    op.create_index("ix_post_quality_reports_company_id", "post_quality_reports", ["company_id"], unique=False)
    op.create_index("ix_post_quality_reports_project_id", "post_quality_reports", ["project_id"], unique=False)

    op.create_table(
        "ai_generation_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("post_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("input_context", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("output", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["post_id"], ["posts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_generation_logs_company_id", "ai_generation_logs", ["company_id"], unique=False)
    op.create_index("ix_ai_generation_logs_project_id", "ai_generation_logs", ["project_id"], unique=False)
    op.create_index("ix_ai_generation_logs_post_id", "ai_generation_logs", ["post_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_ai_generation_logs_post_id", table_name="ai_generation_logs")
    op.drop_index("ix_ai_generation_logs_project_id", table_name="ai_generation_logs")
    op.drop_index("ix_ai_generation_logs_company_id", table_name="ai_generation_logs")
    op.drop_table("ai_generation_logs")

    op.drop_index("ix_post_quality_reports_project_id", table_name="post_quality_reports")
    op.drop_index("ix_post_quality_reports_company_id", table_name="post_quality_reports")
    op.drop_index("ix_post_quality_reports_post_id", table_name="post_quality_reports")
    op.drop_table("post_quality_reports")

    op.drop_index("uq_brand_profiles_company_default", table_name="brand_profiles")
    op.drop_index("ix_brand_profiles_project_id", table_name="brand_profiles")
    op.drop_index("ix_brand_profiles_company_id", table_name="brand_profiles")
    op.drop_table("brand_profiles")

    op.drop_constraint("ck_posts_status_values", "posts", type_="check")
    op.create_check_constraint(
        "ck_posts_status_values",
        "posts",
        "status IN ('draft', 'scheduled', 'publishing', 'published', 'published_partial', 'failed')",
    )
