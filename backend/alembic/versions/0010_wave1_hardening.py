"""add wave1 hardening tables

Revision ID: 0010_wave1_hardening
Revises: 0009_automation_schema
Create Date: 2026-02-16 00:20:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0010_wave1_hardening"
down_revision = "0009_automation_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "failed_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_type", sa.String(length=64), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("error_message", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_failed_jobs_job_type", "failed_jobs", ["job_type"], unique=False)

    op.create_table(
        "revoked_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_id", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_id", name="uq_revoked_tokens_token_id"),
    )
    op.create_index("ix_revoked_tokens_token_id", "revoked_tokens", ["token_id"], unique=True)
    op.create_index("ix_revoked_tokens_expires_at", "revoked_tokens", ["expires_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_revoked_tokens_expires_at", table_name="revoked_tokens")
    op.drop_index("ix_revoked_tokens_token_id", table_name="revoked_tokens")
    op.drop_table("revoked_tokens")

    op.drop_index("ix_failed_jobs_job_type", table_name="failed_jobs")
    op.drop_table("failed_jobs")
