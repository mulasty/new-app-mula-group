import uuid
from decimal import Decimal

from sqlalchemy import DateTime, Float, ForeignKey, Numeric, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base


class RevenueMetric(Base):
    __tablename__ = "revenue_metrics"
    __table_args__ = (UniqueConstraint("company_id", name="uq_revenue_metrics_company"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    mrr: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0.00"))
    plan: Mapped[str] = mapped_column(String(64), nullable=False, default="Starter")
    usage_percent: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    churn_risk_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    upgrade_probability: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    overuse_detected: Mapped[bool] = mapped_column(nullable=False, default=False)
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
