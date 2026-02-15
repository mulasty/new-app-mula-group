import uuid
from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base


class ChannelType(StrEnum):
    WEBSITE = "website"


class ChannelStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


class Channel(Base):
    __tablename__ = "channels"
    __table_args__ = (
        UniqueConstraint("company_id", "project_id", "type", name="uq_channels_company_project_type"),
        CheckConstraint("status IN ('active', 'disabled')", name="ck_channels_status_values"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(String(32), nullable=False, default=ChannelType.WEBSITE.value)
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="Website")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=ChannelStatus.ACTIVE.value)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
