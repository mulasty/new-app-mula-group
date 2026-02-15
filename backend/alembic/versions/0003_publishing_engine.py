"""add publishing engine tables

Revision ID: 0003_publishing_engine
Revises: 0002_rbac_signup
Create Date: 2026-02-15 00:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0003_publishing_engine"
down_revision = "0002_rbac_signup"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "channels",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False, server_default="Website"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "project_id", "type", name="uq_channels_company_project_type"),
    )
    op.create_check_constraint("ck_channels_status_values", "channels", "status IN ('active', 'disabled')")
    op.create_index("ix_channels_company_id", "channels", ["company_id"], unique=False)
    op.create_index("ix_channels_project_id", "channels", ["project_id"], unique=False)

    op.create_table(
        "posts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("publish_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_check_constraint(
        "ck_posts_status_values",
        "posts",
        "status IN ('draft', 'scheduled', 'publishing', 'published', 'failed')",
    )
    op.create_index("ix_posts_company_id", "posts", ["company_id"], unique=False)
    op.create_index("ix_posts_project_id", "posts", ["project_id"], unique=False)

    op.create_table(
        "publish_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("post_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["channel_id"], ["channels.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["post_id"], ["posts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_check_constraint("ck_publish_events_status_values", "publish_events", "status IN ('ok', 'error')")
    op.create_index("ix_publish_events_company_id", "publish_events", ["company_id"], unique=False)
    op.create_index("ix_publish_events_project_id", "publish_events", ["project_id"], unique=False)
    op.create_index("ix_publish_events_post_id", "publish_events", ["post_id"], unique=False)

    op.create_table(
        "website_publications",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("post_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["post_id"], ["posts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "slug", name="uq_website_publications_company_slug"),
    )
    op.create_index("ix_website_publications_company_id", "website_publications", ["company_id"], unique=False)
    op.create_index("ix_website_publications_project_id", "website_publications", ["project_id"], unique=False)
    op.create_index("ix_website_publications_post_id", "website_publications", ["post_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_website_publications_post_id", table_name="website_publications")
    op.drop_index("ix_website_publications_project_id", table_name="website_publications")
    op.drop_index("ix_website_publications_company_id", table_name="website_publications")
    op.drop_table("website_publications")

    op.drop_index("ix_publish_events_post_id", table_name="publish_events")
    op.drop_index("ix_publish_events_project_id", table_name="publish_events")
    op.drop_index("ix_publish_events_company_id", table_name="publish_events")
    op.drop_constraint("ck_publish_events_status_values", "publish_events", type_="check")
    op.drop_table("publish_events")

    op.drop_index("ix_posts_project_id", table_name="posts")
    op.drop_index("ix_posts_company_id", table_name="posts")
    op.drop_constraint("ck_posts_status_values", "posts", type_="check")
    op.drop_table("posts")

    op.drop_index("ix_channels_project_id", table_name="channels")
    op.drop_index("ix_channels_company_id", table_name="channels")
    op.drop_constraint("ck_channels_status_values", "channels", type_="check")
    op.drop_table("channels")
