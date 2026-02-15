"""add platform rate limits and publish event indexes

Revision ID: 0008_universal_connector
Revises: 0007_meta_connector
Create Date: 2026-02-15 22:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0008_universal_connector"
down_revision = "0007_meta_connector"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "platform_rate_limits",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("requests_per_minute", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("platform", name="uq_platform_rate_limits_platform"),
    )
    op.create_index("ix_platform_rate_limits_platform", "platform_rate_limits", ["platform"], unique=True)

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_publish_events_company_project_created_at
        ON publish_events (company_id, project_id, created_at)
        """
    )

    op.execute(
        """
        INSERT INTO platform_rate_limits (id, platform, requests_per_minute)
        VALUES
            ('77777777-7777-4777-8777-777777777777', 'website', 600),
            ('88888888-8888-4888-8888-888888888888', 'linkedin', 120),
            ('99999999-9999-4999-8999-999999999999', 'facebook', 180),
            ('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', 'instagram', 120),
            ('bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb', 'tiktok', 120),
            ('cccccccc-cccc-4ccc-8ccc-cccccccccccc', 'threads', 120),
            ('dddddddd-dddd-4ddd-8ddd-dddddddddddd', 'x', 120),
            ('eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee', 'pinterest', 90),
            ('ffffffff-ffff-4fff-8fff-ffffffffffff', 'youtube', 120)
        ON CONFLICT (platform) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index("ix_platform_rate_limits_platform", table_name="platform_rate_limits")
    op.drop_table("platform_rate_limits")
