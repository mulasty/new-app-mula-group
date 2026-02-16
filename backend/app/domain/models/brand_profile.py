import uuid

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base


class BrandProfile(Base):
    __tablename__ = "brand_profiles"
    __table_args__ = (
        UniqueConstraint("company_id", "project_id", name="uq_brand_profiles_company_project"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True
    )
    brand_name: Mapped[str] = mapped_column(String(255), nullable=False)
    language: Mapped[str] = mapped_column(String(16), nullable=False, default="pl")
    tone: Mapped[str] = mapped_column(String(32), nullable=False, default="professional")
    target_audience: Mapped[str | None] = mapped_column(Text, nullable=True)
    do_list: Mapped[list[str]] = mapped_column(ARRAY(String(255)), nullable=False, default=list)
    dont_list: Mapped[list[str]] = mapped_column(ARRAY(String(255)), nullable=False, default=list)
    forbidden_claims: Mapped[list[str]] = mapped_column(ARRAY(String(255)), nullable=False, default=list)
    preferred_hashtags: Mapped[list[str]] = mapped_column(ARRAY(String(128)), nullable=False, default=list)
    compliance_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
