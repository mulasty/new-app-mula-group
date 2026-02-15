import uuid
from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base


class RetryBackoffStrategy(StrEnum):
    LINEAR = "linear"
    EXPONENTIAL = "exponential"


class ChannelRetryPolicy(Base):
    __tablename__ = "channel_retry_policies"
    __table_args__ = (
        UniqueConstraint("channel_type", name="uq_channel_retry_policies_channel_type"),
        CheckConstraint(
            "backoff_strategy IN ('linear', 'exponential')",
            name="ck_channel_retry_policies_backoff_strategy",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    channel_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    backoff_strategy: Mapped[str] = mapped_column(
        String(32), nullable=False, default=RetryBackoffStrategy.EXPONENTIAL.value
    )
    retry_delay_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
