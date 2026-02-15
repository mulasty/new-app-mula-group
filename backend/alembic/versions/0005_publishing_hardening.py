"""add publishing hardening tables and post partial status

Revision ID: 0005_publishing_hardening
Revises: 0004_connector_foundation_social_accounts
Create Date: 2026-02-16 00:20:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0005_publishing_hardening"
down_revision = "0004_connector_foundation_social_accounts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_posts_status_values", "posts", type_="check")
    op.create_check_constraint(
        "ck_posts_status_values",
        "posts",
        "status IN ('draft', 'scheduled', 'publishing', 'published', 'published_partial', 'failed')",
    )

    op.create_table(
        "channel_retry_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel_type", sa.String(length=32), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("backoff_strategy", sa.String(length=32), nullable=False, server_default="exponential"),
        sa.Column("retry_delay_seconds", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("channel_type", name="uq_channel_retry_policies_channel_type"),
    )
    op.create_check_constraint(
        "ck_channel_retry_policies_backoff_strategy",
        "channel_retry_policies",
        "backoff_strategy IN ('linear', 'exponential')",
    )
    op.create_index(
        "ix_channel_retry_policies_channel_type",
        "channel_retry_policies",
        ["channel_type"],
        unique=True,
    )

    op.execute(
        """
        INSERT INTO channel_retry_policies (id, channel_type, max_attempts, backoff_strategy, retry_delay_seconds)
        VALUES
            ('11111111-1111-4111-8111-111111111111', 'website', 5, 'exponential', 30),
            ('22222222-2222-4222-8222-222222222222', 'linkedin', 5, 'exponential', 45)
        ON CONFLICT (channel_type) DO NOTHING
        """
    )

    op.create_table(
        "channel_publications",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("post_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("external_post_id", sa.String(length=255), nullable=False),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["channel_id"], ["channels.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["post_id"], ["posts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "post_id",
            "channel_id",
            name="uq_channel_publications_company_post_channel",
        ),
        sa.UniqueConstraint(
            "company_id",
            "channel_id",
            "external_post_id",
            name="uq_channel_publications_company_channel_external",
        ),
    )
    op.create_index("ix_channel_publications_company_id", "channel_publications", ["company_id"], unique=False)
    op.create_index("ix_channel_publications_project_id", "channel_publications", ["project_id"], unique=False)
    op.create_index("ix_channel_publications_post_id", "channel_publications", ["post_id"], unique=False)
    op.create_index("ix_channel_publications_channel_id", "channel_publications", ["channel_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_channel_publications_channel_id", table_name="channel_publications")
    op.drop_index("ix_channel_publications_post_id", table_name="channel_publications")
    op.drop_index("ix_channel_publications_project_id", table_name="channel_publications")
    op.drop_index("ix_channel_publications_company_id", table_name="channel_publications")
    op.drop_table("channel_publications")

    op.drop_index("ix_channel_retry_policies_channel_type", table_name="channel_retry_policies")
    op.drop_constraint("ck_channel_retry_policies_backoff_strategy", "channel_retry_policies", type_="check")
    op.drop_table("channel_retry_policies")

    op.drop_constraint("ck_posts_status_values", "posts", type_="check")
    op.create_check_constraint(
        "ck_posts_status_values",
        "posts",
        "status IN ('draft', 'scheduled', 'publishing', 'published', 'failed')",
    )
