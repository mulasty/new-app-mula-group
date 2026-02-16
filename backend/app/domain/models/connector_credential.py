import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base


class ConnectorCredential(Base):
    __tablename__ = "connector_credentials"
    __table_args__ = (
        UniqueConstraint("tenant_id", "connector_type", name="uq_connector_credentials_tenant_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    connector_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    encrypted_access_token: Mapped[str | None] = mapped_column(String(4096), nullable=True)
    encrypted_refresh_token: Mapped[str | None] = mapped_column(String(4096), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scopes: Mapped[list[str]] = mapped_column(ARRAY(String(128)), nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    last_error: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
