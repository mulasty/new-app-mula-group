from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import decrypt_secret, encrypt_secret
from app.domain.models.connector_credential import ConnectorCredential
from app.domain.models.social_account import SocialAccount


def upsert_connector_credential(
    db: Session,
    *,
    tenant_id: UUID,
    connector_type: str,
    access_token: str | None,
    refresh_token: str | None,
    expires_at: datetime | None,
    scopes: list[str] | None = None,
    status: str = "active",
    last_error: str | None = None,
) -> ConnectorCredential:
    normalized = connector_type.strip().lower()
    row = db.execute(
        select(ConnectorCredential).where(
            ConnectorCredential.tenant_id == tenant_id,
            ConnectorCredential.connector_type == normalized,
        )
    ).scalar_one_or_none()
    if row is None:
        row = ConnectorCredential(
            tenant_id=tenant_id,
            connector_type=normalized,
            encrypted_access_token=encrypt_secret(access_token) if access_token else None,
            encrypted_refresh_token=encrypt_secret(refresh_token) if refresh_token else None,
            expires_at=expires_at,
            scopes=scopes or [],
            status=status,
            last_error=last_error,
        )
    else:
        if access_token:
            row.encrypted_access_token = encrypt_secret(access_token)
        if refresh_token:
            row.encrypted_refresh_token = encrypt_secret(refresh_token)
        row.expires_at = expires_at if expires_at is not None else row.expires_at
        row.scopes = scopes or row.scopes or []
        row.status = status
        row.last_error = last_error
    db.add(row)
    return row


def sync_credential_from_social_account(db: Session, *, account: SocialAccount, scopes: list[str] | None = None) -> None:
    upsert_connector_credential(
        db,
        tenant_id=account.company_id,
        connector_type=account.platform,
        access_token=(decrypt_secret(account.access_token) if account.access_token else None),
        refresh_token=(decrypt_secret(account.refresh_token) if account.refresh_token else None),
        expires_at=account.expires_at,
        scopes=scopes,
        status="active",
    )


def get_connector_credential(db: Session, *, tenant_id: UUID, connector_type: str) -> ConnectorCredential | None:
    return db.execute(
        select(ConnectorCredential).where(
            ConnectorCredential.tenant_id == tenant_id,
            ConnectorCredential.connector_type == connector_type.strip().lower(),
        )
    ).scalar_one_or_none()


def mark_connector_credential_error(
    db: Session,
    *,
    tenant_id: UUID,
    connector_type: str,
    message: str,
    status: str = "error",
) -> None:
    credential = get_connector_credential(db, tenant_id=tenant_id, connector_type=connector_type)
    if credential is None:
        return
    credential.last_error = message[:512]
    credential.status = status
    db.add(credential)


def revoke_connector_credential(db: Session, *, tenant_id: UUID, connector_type: str) -> None:
    credential = get_connector_credential(db, tenant_id=tenant_id, connector_type=connector_type)
    if credential is None:
        return
    credential.status = "revoked"
    credential.last_error = None
    db.add(credential)


def is_credential_revoked(db: Session, *, tenant_id: UUID, connector_type: str) -> bool:
    credential = get_connector_credential(db, tenant_id=tenant_id, connector_type=connector_type)
    return bool(credential and credential.status == "revoked")


def is_credential_expiring(
    db: Session,
    *,
    tenant_id: UUID,
    connector_type: str,
    within_seconds: int = 60,
) -> bool:
    credential = get_connector_credential(db, tenant_id=tenant_id, connector_type=connector_type)
    if credential is None or credential.expires_at is None:
        return False
    return credential.expires_at <= datetime.now(UTC) + timedelta(seconds=within_seconds)
