"""add v1 activation template and billing lifecycle tables

Revision ID: 0015_v1_activation_ux
Revises: 0014_phase8_ops_core
Create Date: 2026-02-16 02:20:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "0015_v1_activation_ux"
down_revision = "0014_phase8_ops_core"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "content_templates",
        sa.Column("category", sa.String(length=64), nullable=False, server_default="educational"),
    )
    op.add_column(
        "content_templates",
        sa.Column("tone", sa.String(length=64), nullable=False, server_default="professional"),
    )
    op.add_column(
        "content_templates",
        sa.Column("content_structure", sa.Text(), nullable=False, server_default=""),
    )
    op.create_index("ix_content_templates_category", "content_templates", ["category"], unique=False)

    op.create_table(
        "billing_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_billing_events_company_id", "billing_events", ["company_id"], unique=False)
    op.create_index("ix_billing_events_event_type", "billing_events", ["event_type"], unique=False)
    op.create_index("ix_billing_events_created_at", "billing_events", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_billing_events_created_at", table_name="billing_events")
    op.drop_index("ix_billing_events_event_type", table_name="billing_events")
    op.drop_index("ix_billing_events_company_id", table_name="billing_events")
    op.drop_table("billing_events")

    op.drop_index("ix_content_templates_category", table_name="content_templates")
    op.drop_column("content_templates", "content_structure")
    op.drop_column("content_templates", "tone")
    op.drop_column("content_templates", "category")
