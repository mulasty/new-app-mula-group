import uuid
from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base


class ContentTemplateType(StrEnum):
    POST_TEXT = "post_text"
    CAROUSEL_PLAN = "carousel_plan"
    VIDEO_SCRIPT = "video_script"


class ContentTemplate(Base):
    __tablename__ = "content_templates"
    __table_args__ = (
        CheckConstraint(
            "template_type IN ('post_text', 'carousel_plan', 'video_script')",
            name="ck_content_templates_type_values",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    template_type: Mapped[str] = mapped_column(String(32), nullable=False, default=ContentTemplateType.POST_TEXT.value)
    prompt_template: Mapped[str] = mapped_column(Text, nullable=False)
    output_schema_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    default_values_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
