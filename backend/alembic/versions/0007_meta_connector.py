"""add meta connector tables and channel capabilities

Revision ID: 0007_meta_connector
Revises: 0006_linkedin_connector
Create Date: 2026-02-15 20:30:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0007_meta_connector"
down_revision = "0006_linkedin_connector"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "channels",
        sa.Column(
            "capabilities_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.execute(
        """
        UPDATE channels
        SET capabilities_json = CASE type
            WHEN 'website' THEN '{"text": true, "image": true, "video": true, "reels": false, "shorts": false, "max_length": 50000}'::jsonb
            WHEN 'linkedin' THEN '{"text": true, "image": true, "video": false, "reels": false, "shorts": false, "max_length": 3000}'::jsonb
            ELSE '{}'::jsonb
        END
        """
    )
    op.alter_column("channels", "capabilities_json", server_default=None)

    op.create_table(
        "facebook_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("facebook_user_id", sa.String(length=128), nullable=False),
        sa.Column("access_token", sa.String(length=2048), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "facebook_user_id", name="uq_facebook_accounts_company_user"),
    )
    op.create_index("ix_facebook_accounts_company_id", "facebook_accounts", ["company_id"], unique=False)

    op.create_table(
        "facebook_pages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("page_id", sa.String(length=128), nullable=False),
        sa.Column("page_name", sa.String(length=255), nullable=False),
        sa.Column("access_token", sa.String(length=2048), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "page_id", name="uq_facebook_pages_company_page"),
    )
    op.create_index("ix_facebook_pages_company_id", "facebook_pages", ["company_id"], unique=False)

    op.create_table(
        "instagram_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("instagram_account_id", sa.String(length=128), nullable=False),
        sa.Column("username", sa.String(length=255), nullable=True),
        sa.Column("linked_page_id", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "instagram_account_id", name="uq_instagram_accounts_company_account"),
    )
    op.create_index("ix_instagram_accounts_company_id", "instagram_accounts", ["company_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_instagram_accounts_company_id", table_name="instagram_accounts")
    op.drop_table("instagram_accounts")

    op.drop_index("ix_facebook_pages_company_id", table_name="facebook_pages")
    op.drop_table("facebook_pages")

    op.drop_index("ix_facebook_accounts_company_id", table_name="facebook_accounts")
    op.drop_table("facebook_accounts")

    op.drop_column("channels", "capabilities_json")
