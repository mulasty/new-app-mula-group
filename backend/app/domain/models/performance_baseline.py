import uuid

from sqlalchemy import Boolean, DateTime, Float, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base


class PerformanceBaseline(Base):
    __tablename__ = "performance_baselines"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    component: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    metric_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    avg_value: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    p95_value: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    regression_detected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    recorded_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
