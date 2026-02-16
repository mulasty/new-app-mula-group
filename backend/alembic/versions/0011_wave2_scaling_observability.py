"""add wave2 scaling and scheduler indexes

Revision ID: 0011_wave2_scaling_observability
Revises: 0010_wave1_hardening
Create Date: 2026-02-16 02:10:00
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0011_wave2_scaling_observability"
down_revision = "0010_wave1_hardening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_posts_status_publish_at",
        "posts",
        ["status", "publish_at"],
        unique=False,
    )
    op.create_index(
        "ix_posts_company_status",
        "posts",
        ["company_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_posts_scheduled_publish_at_partial",
        "posts",
        ["publish_at"],
        unique=False,
        postgresql_where=sa.text("status = 'scheduled'"),
    )


def downgrade() -> None:
    op.drop_index("ix_posts_scheduled_publish_at_partial", table_name="posts")
    op.drop_index("ix_posts_company_status", table_name="posts")
    op.drop_index("ix_posts_status_publish_at", table_name="posts")
