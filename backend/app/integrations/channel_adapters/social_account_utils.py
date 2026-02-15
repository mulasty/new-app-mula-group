from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.orm import Session

from app.application.services.social_account_service import (
    get_social_account_for_company,
    update_social_account_tokens,
)
from app.core.security import decrypt_secret
from app.domain.models.social_account import SocialAccount


def load_platform_account(
    db: Session,
    *,
    company_id: UUID,
    platform: str,
    preferred_external_account_id: str | None = None,
) -> SocialAccount | None:
    return get_social_account_for_company(
        db,
        company_id=company_id,
        platform=platform,
        external_account_id=preferred_external_account_id,
    )


def decrypted_access_token(account: SocialAccount) -> str:
    if not account.access_token:
        return ""
    return decrypt_secret(account.access_token)


def decrypted_refresh_token(account: SocialAccount) -> str:
    if not account.refresh_token:
        return ""
    return decrypt_secret(account.refresh_token)


def is_token_expiring(account: SocialAccount, *, within_seconds: int = 60) -> bool:
    if account.expires_at is None:
        return False
    return account.expires_at <= datetime.now(UTC) + timedelta(seconds=within_seconds)


def persist_tokens(
    db: Session,
    *,
    account: SocialAccount,
    access_token: str | None,
    refresh_token: str | None,
    expires_in_seconds: int | None = None,
) -> SocialAccount:
    expires_at = None
    if expires_in_seconds is not None:
        expires_at = datetime.now(UTC) + timedelta(seconds=max(1, int(expires_in_seconds)))
    updated = update_social_account_tokens(
        db,
        account=account,
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=expires_at,
    )
    db.flush()
    return updated
