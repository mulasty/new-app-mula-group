from uuid import UUID

from sqlalchemy.orm import Session

from app.domain.models.audit_log import AuditLog


def log_audit_event(db: Session, *, company_id: UUID, action: str, metadata: dict | None = None) -> None:
    db.add(
        AuditLog(
            company_id=company_id,
            action=action,
            metadata_json=metadata or {},
        )
    )
