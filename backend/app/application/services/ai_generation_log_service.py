from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.domain.models.ai_generation_log import AIGenerationLog


def log_ai_generation(
    db: Session,
    *,
    tenant_id: UUID,
    project_id: UUID,
    model: str,
    input_context: dict[str, Any],
    output: dict[str, Any],
    post_id: UUID | None = None,
) -> AIGenerationLog:
    log = AIGenerationLog(
        company_id=tenant_id,
        project_id=project_id,
        post_id=post_id,
        input_context=input_context,
        output=output,
        model=model,
    )
    db.add(log)
    db.flush()
    return log
