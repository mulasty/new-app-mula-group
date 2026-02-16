from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.security import get_token_identifier
from app.domain.models.revoked_token import RevokedToken


def revoke_token(db: Session, *, token: str, expires_at: datetime, claims: dict | None = None) -> None:
    token_id = get_token_identifier(token, claims)
    existing = db.execute(select(RevokedToken).where(RevokedToken.token_id == token_id)).scalar_one_or_none()
    if existing is None:
        db.add(RevokedToken(token_id=token_id, expires_at=expires_at))


def is_token_revoked(db: Session, *, token: str, claims: dict | None = None) -> bool:
    token_id = get_token_identifier(token, claims)
    row = db.execute(select(RevokedToken).where(RevokedToken.token_id == token_id)).scalar_one_or_none()
    if row is None:
        return False
    now = datetime.now(timezone.utc)
    return row.expires_at >= now


def prune_expired_revoked_tokens(db: Session) -> None:
    now = datetime.now(timezone.utc)
    db.execute(delete(RevokedToken).where(RevokedToken.expires_at < now))
