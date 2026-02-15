from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import encrypt_secret
from app.domain.models.social_account import SocialAccount


def upsert_social_account(
    db: Session,
    *,
    company_id: UUID,
    platform: str,
    external_account_id: str,
    display_name: str | None = None,
    access_token: str | None = None,
    refresh_token: str | None = None,
    expires_at: datetime | None = None,
    metadata_json: dict | None = None,
) -> SocialAccount:
    normalized_platform = platform.strip().lower()
    account = db.execute(
        select(SocialAccount).where(
            SocialAccount.company_id == company_id,
            SocialAccount.platform == normalized_platform,
            SocialAccount.external_account_id == external_account_id,
        )
    ).scalar_one_or_none()

    if account is None:
        account = SocialAccount(
            company_id=company_id,
            platform=normalized_platform,
            external_account_id=external_account_id,
            display_name=display_name,
            access_token=(encrypt_secret(access_token) if access_token else None),
            refresh_token=(encrypt_secret(refresh_token) if refresh_token else None),
            expires_at=expires_at,
            metadata_json=metadata_json or {},
        )
    else:
        account.display_name = display_name
        account.access_token = encrypt_secret(access_token) if access_token else account.access_token
        account.refresh_token = (
            encrypt_secret(refresh_token) if refresh_token else account.refresh_token
        )
        account.expires_at = expires_at if expires_at is not None else account.expires_at
        account.metadata_json = metadata_json or account.metadata_json or {}

    db.add(account)
    return account


def get_social_account_for_company(
    db: Session,
    *,
    company_id: UUID,
    platform: str,
    external_account_id: str | None = None,
) -> SocialAccount | None:
    normalized_platform = platform.strip().lower()
    query = select(SocialAccount).where(
        SocialAccount.company_id == company_id,
        SocialAccount.platform == normalized_platform,
    )
    if external_account_id:
        query = query.where(SocialAccount.external_account_id == external_account_id)
    return db.execute(query.order_by(SocialAccount.created_at.asc())).scalars().first()


def update_social_account_tokens(
    db: Session,
    *,
    account: SocialAccount,
    access_token: str | None,
    refresh_token: str | None,
    expires_at: datetime | None = None,
) -> SocialAccount:
    if access_token:
        account.access_token = encrypt_secret(access_token)
    if refresh_token:
        account.refresh_token = encrypt_secret(refresh_token)
    if expires_at is not None:
        account.expires_at = expires_at
    db.add(account)
    return account
