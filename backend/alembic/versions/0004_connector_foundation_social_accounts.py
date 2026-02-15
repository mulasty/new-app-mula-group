"""add universal social_accounts model

Revision ID: 0004_social_accounts
Revises: 0003_publishing_engine
Create Date: 2026-02-15 23:40:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0004_social_accounts"
down_revision = "0003_publishing_engine"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "social_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("external_account_id", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("access_token", sa.String(length=2048), nullable=True),
        sa.Column("refresh_token", sa.String(length=2048), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "platform",
            "external_account_id",
            name="uq_social_accounts_company_platform_external",
        ),
    )
    op.create_index("ix_social_accounts_company_id", "social_accounts", ["company_id"], unique=False)
    op.create_index("ix_social_accounts_platform", "social_accounts", ["platform"], unique=False)
    op.create_index(
        "ix_social_accounts_company_platform",
        "social_accounts",
        ["company_id", "platform"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_social_accounts_company_platform", table_name="social_accounts")
    op.drop_index("ix_social_accounts_platform", table_name="social_accounts")
    op.drop_index("ix_social_accounts_company_id", table_name="social_accounts")
    op.drop_table("social_accounts")
