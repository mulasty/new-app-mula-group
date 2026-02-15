"""add linkedin accounts table

Revision ID: 0006_linkedin_connector
Revises: 0005_publishing_hardening
Create Date: 2026-02-15 18:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0006_linkedin_connector"
down_revision = "0005_publishing_hardening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "linkedin_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("linkedin_member_id", sa.String(length=128), nullable=False),
        sa.Column("access_token", sa.String(length=2048), nullable=False),
        sa.Column("refresh_token", sa.String(length=2048), nullable=False, server_default=""),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", name="uq_linkedin_accounts_company"),
    )
    op.create_index("ix_linkedin_accounts_company_id", "linkedin_accounts", ["company_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_linkedin_accounts_company_id", table_name="linkedin_accounts")
    op.drop_table("linkedin_accounts")
