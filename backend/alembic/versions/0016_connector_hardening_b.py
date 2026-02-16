"""add connector credentials for oauth hardening

Revision ID: 0016_connector_hardening_b
Revises: 0015_v1_activation_ux
Create Date: 2026-02-16 03:05:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "0016_connector_hardening_b"
down_revision = "0015_v1_activation_ux"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "connector_credentials",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("connector_type", sa.String(length=32), nullable=False),
        sa.Column("encrypted_access_token", sa.String(length=4096), nullable=True),
        sa.Column("encrypted_refresh_token", sa.String(length=4096), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scopes", postgresql.ARRAY(sa.String(length=128)), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("last_error", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["tenant_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "connector_type", name="uq_connector_credentials_tenant_type"),
    )
    op.create_index("ix_connector_credentials_tenant_id", "connector_credentials", ["tenant_id"], unique=False)
    op.create_index("ix_connector_credentials_connector_type", "connector_credentials", ["connector_type"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_connector_credentials_connector_type", table_name="connector_credentials")
    op.drop_index("ix_connector_credentials_tenant_id", table_name="connector_credentials")
    op.drop_table("connector_credentials")
