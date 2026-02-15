import uuid
from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base


class AutomationTriggerType(StrEnum):
    CRON = "cron"
    INTERVAL = "interval"
    EVENT = "event"


class AutomationActionType(StrEnum):
    GENERATE_POST = "generate_post"
    SCHEDULE_POST = "schedule_post"
    PUBLISH_NOW = "publish_now"
    SYNC_METRICS = "sync_metrics"


class AutomationRule(Base):
    __tablename__ = "automation_rules"
    __table_args__ = (
        CheckConstraint(
            "trigger_type IN ('cron', 'interval', 'event')",
            name="ck_automation_rules_trigger_values",
        ),
        CheckConstraint(
            "action_type IN ('generate_post', 'schedule_post', 'publish_now', 'sync_metrics')",
            name="ck_automation_rules_action_values",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(nullable=False, default=True)
    trigger_type: Mapped[str] = mapped_column(String(32), nullable=False)
    trigger_config_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    action_type: Mapped[str] = mapped_column(String(32), nullable=False)
    action_config_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    guardrails_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
