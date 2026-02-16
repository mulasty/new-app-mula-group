import uuid

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base


class TenantRiskScore(Base):
    __tablename__ = "tenant_risk_scores"
    __table_args__ = (UniqueConstraint("company_id", name="uq_tenant_risk_scores_company"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    risk_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    publish_failure_ratio: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    flagged_content_ratio: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    abuse_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    rate_limit_violations: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False, default="low")
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
