from datetime import UTC, datetime, timedelta
from uuid import UUID

import httpx
import jwt
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.services.social_account_service import upsert_social_account
from app.core.config import settings
from app.core.security import encrypt_secret
from app.domain.models.channel import Channel, ChannelType
from app.domain.models.facebook_account import FacebookAccount
from app.domain.models.facebook_page import FacebookPage
from app.domain.models.instagram_account import InstagramAccount
from app.domain.models.project import Project
from app.integrations.channel_adapters import get_adapter_capabilities


def _require_meta_config() -> None:
    if not settings.meta_app_id or not settings.meta_app_secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Meta OAuth is not configured",
        )


def _create_state(*, company_id: UUID, project_id: UUID, user_id: UUID) -> str:
    expires_at = datetime.now(UTC) + timedelta(minutes=10)
    payload = {
        "type": "meta_oauth_state",
        "company_id": str(company_id),
        "project_id": str(project_id),
        "user_id": str(user_id),
        "exp": expires_at,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_state(state: str) -> dict:
    try:
        payload = jwt.decode(state, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OAuth state") from exc

    if payload.get("type") != "meta_oauth_state":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OAuth state type")
    return payload


def resolve_project_for_meta(db: Session, *, company_id: UUID, project_id: UUID | None) -> Project:
    if project_id is not None:
        project = db.execute(
            select(Project).where(Project.id == project_id, Project.company_id == company_id)
        ).scalar_one_or_none()
        if project is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
        return project

    project = db.execute(
        select(Project).where(Project.company_id == company_id).order_by(Project.created_at.asc())
    ).scalar_one_or_none()
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Create a project before connecting Meta channels",
        )
    return project


def build_oauth_authorization_url(*, company_id: UUID, project_id: UUID, user_id: UUID) -> str:
    _require_meta_config()
    state = _create_state(company_id=company_id, project_id=project_id, user_id=user_id)
    params = {
        "client_id": settings.meta_app_id,
        "redirect_uri": settings.meta_redirect_uri,
        "scope": settings.meta_oauth_scope,
        "response_type": "code",
        "state": state,
    }
    return str(httpx.URL("https://www.facebook.com/v21.0/dialog/oauth", params=params))


def exchange_code_for_user_token(code: str) -> dict:
    _require_meta_config()
    params = {
        "client_id": settings.meta_app_id,
        "client_secret": settings.meta_app_secret,
        "redirect_uri": settings.meta_redirect_uri,
        "code": code,
    }
    with httpx.Client(timeout=20.0) as client:
        response = client.get(f"{settings.meta_graph_api_base_url}/oauth/access_token", params=params)
        if response.status_code >= 400:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Meta token exchange failed: {response.status_code}",
            )
        return response.json()


def exchange_for_long_lived_user_token(short_lived_token: str) -> dict:
    _require_meta_config()
    params = {
        "grant_type": "fb_exchange_token",
        "client_id": settings.meta_app_id,
        "client_secret": settings.meta_app_secret,
        "fb_exchange_token": short_lived_token,
    }
    with httpx.Client(timeout=20.0) as client:
        response = client.get(f"{settings.meta_graph_api_base_url}/oauth/access_token", params=params)
        if response.status_code >= 400:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Meta long-lived token exchange failed: {response.status_code}",
            )
        return response.json()


def fetch_meta_user_profile(user_access_token: str) -> dict:
    params = {"fields": "id", "access_token": user_access_token}
    with httpx.Client(timeout=20.0) as client:
        response = client.get(f"{settings.meta_graph_api_base_url}/me", params=params)
        if response.status_code >= 400:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Meta user profile fetch failed: {response.status_code}",
            )
        return response.json()


def fetch_facebook_pages(user_access_token: str) -> list[dict]:
    params = {"fields": "id,name,access_token", "access_token": user_access_token}
    pages: list[dict] = []
    next_url: str | None = f"{settings.meta_graph_api_base_url}/me/accounts"

    with httpx.Client(timeout=20.0) as client:
        while next_url:
            response = client.get(next_url, params=params if next_url.endswith("/me/accounts") else None)
            if response.status_code >= 400:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Facebook pages fetch failed: {response.status_code}",
                )
            payload = response.json()
            pages.extend(payload.get("data", []))
            paging = payload.get("paging") or {}
            next_url = paging.get("next")
            params = None

    return pages


def fetch_instagram_accounts_for_pages(pages: list[dict]) -> list[dict]:
    accounts: list[dict] = []
    with httpx.Client(timeout=20.0) as client:
        for page in pages:
            page_id = str(page.get("id") or "")
            page_token = str(page.get("access_token") or "")
            if not page_id or not page_token:
                continue

            params = {
                "fields": "instagram_business_account{id,username}",
                "access_token": page_token,
            }
            response = client.get(f"{settings.meta_graph_api_base_url}/{page_id}", params=params)
            if response.status_code >= 400:
                continue
            payload = response.json()
            instagram_account = payload.get("instagram_business_account")
            if not instagram_account:
                continue

            instagram_id = str(instagram_account.get("id") or "")
            if not instagram_id:
                continue
            accounts.append(
                {
                    "instagram_account_id": instagram_id,
                    "username": instagram_account.get("username"),
                    "linked_page_id": page_id,
                }
            )

    return accounts


def store_meta_connections_and_channels(
    db: Session,
    *,
    company_id: UUID,
    project_id: UUID,
    facebook_user_id: str,
    user_access_token: str,
    user_expires_in_seconds: int,
    pages: list[dict],
    instagram_accounts: list[dict],
) -> dict:
    now = datetime.now(UTC)
    expires_at = now + timedelta(seconds=user_expires_in_seconds)

    account = db.execute(
        select(FacebookAccount).where(
            FacebookAccount.company_id == company_id,
            FacebookAccount.facebook_user_id == facebook_user_id,
        )
    ).scalar_one_or_none()
    if account is None:
        account = FacebookAccount(
            company_id=company_id,
            facebook_user_id=facebook_user_id,
            access_token=encrypt_secret(user_access_token),
            expires_at=expires_at,
        )
    else:
        account.access_token = encrypt_secret(user_access_token)
        account.expires_at = expires_at
    db.add(account)
    upsert_social_account(
        db,
        company_id=company_id,
        platform=ChannelType.FACEBOOK.value,
        external_account_id=facebook_user_id,
        display_name="Meta User",
        access_token=user_access_token,
        refresh_token=None,
        expires_at=expires_at,
        metadata_json={"scope": settings.meta_oauth_scope},
    )

    stored_pages = 0
    for page in pages:
        page_id = str(page.get("id") or "")
        page_name = str(page.get("name") or "").strip() or page_id
        page_token = str(page.get("access_token") or "")
        if not page_id or not page_token:
            continue

        page_row = db.execute(
            select(FacebookPage).where(
                FacebookPage.company_id == company_id,
                FacebookPage.page_id == page_id,
            )
        ).scalar_one_or_none()
        if page_row is None:
            page_row = FacebookPage(
                company_id=company_id,
                page_id=page_id,
                page_name=page_name,
                access_token=encrypt_secret(page_token),
            )
        else:
            page_row.page_name = page_name
            page_row.access_token = encrypt_secret(page_token)
        db.add(page_row)
        upsert_social_account(
            db,
            company_id=company_id,
            platform=ChannelType.FACEBOOK.value,
            external_account_id=page_id,
            display_name=page_name,
            access_token=page_token,
            refresh_token=None,
            expires_at=expires_at,
            metadata_json={"entity": "facebook_page"},
        )
        stored_pages += 1

    stored_instagram_accounts = 0
    for account_data in instagram_accounts:
        instagram_account_id = str(account_data.get("instagram_account_id") or "")
        if not instagram_account_id:
            continue
        username = account_data.get("username")
        linked_page_id = account_data.get("linked_page_id")
        ig_row = db.execute(
            select(InstagramAccount).where(
                InstagramAccount.company_id == company_id,
                InstagramAccount.instagram_account_id == instagram_account_id,
            )
        ).scalar_one_or_none()
        if ig_row is None:
            ig_row = InstagramAccount(
                company_id=company_id,
                instagram_account_id=instagram_account_id,
                username=(str(username).strip() if username else None),
                linked_page_id=(str(linked_page_id).strip() if linked_page_id else None),
            )
        else:
            ig_row.username = (str(username).strip() if username else None)
            ig_row.linked_page_id = (str(linked_page_id).strip() if linked_page_id else None)
        db.add(ig_row)
        upsert_social_account(
            db,
            company_id=company_id,
            platform=ChannelType.INSTAGRAM.value,
            external_account_id=instagram_account_id,
            display_name=(str(username).strip() if username else None),
            access_token=None,
            refresh_token=None,
            expires_at=expires_at,
            metadata_json={
                "linked_page_id": (str(linked_page_id).strip() if linked_page_id else None),
                "entity": "instagram_business_account",
            },
        )
        stored_instagram_accounts += 1

    if stored_pages > 0:
        facebook_capabilities = get_adapter_capabilities(ChannelType.FACEBOOK.value)
        facebook_channel = db.execute(
            select(Channel).where(
                Channel.company_id == company_id,
                Channel.project_id == project_id,
                Channel.type == ChannelType.FACEBOOK.value,
            )
        ).scalar_one_or_none()
        first_page_name = str((pages[0] or {}).get("name") or "Facebook Page").strip()
        if facebook_channel is None:
            facebook_channel = Channel(
                company_id=company_id,
                project_id=project_id,
                type=ChannelType.FACEBOOK.value,
                name=f"Facebook: {first_page_name}",
                status="active",
                capabilities_json=facebook_capabilities,
            )
        else:
            facebook_channel.name = f"Facebook: {first_page_name}"
            facebook_channel.status = "active"
            facebook_channel.capabilities_json = facebook_capabilities
        db.add(facebook_channel)

    if stored_instagram_accounts > 0:
        instagram_capabilities = get_adapter_capabilities(ChannelType.INSTAGRAM.value)
        instagram_channel = db.execute(
            select(Channel).where(
                Channel.company_id == company_id,
                Channel.project_id == project_id,
                Channel.type == ChannelType.INSTAGRAM.value,
            )
        ).scalar_one_or_none()
        first_username = str((instagram_accounts[0] or {}).get("username") or "").strip()
        label = f"Instagram: @{first_username}" if first_username else "Instagram Business"
        if instagram_channel is None:
            instagram_channel = Channel(
                company_id=company_id,
                project_id=project_id,
                type=ChannelType.INSTAGRAM.value,
                name=label,
                status="active",
                capabilities_json=instagram_capabilities,
            )
        else:
            instagram_channel.name = label
            instagram_channel.status = "active"
            instagram_channel.capabilities_json = instagram_capabilities
        db.add(instagram_channel)

    db.commit()
    return {
        "pages_connected": stored_pages,
        "instagram_accounts_connected": stored_instagram_accounts,
    }


def list_meta_connections(db: Session, *, company_id: UUID) -> dict:
    pages = db.execute(
        select(FacebookPage)
        .where(FacebookPage.company_id == company_id)
        .order_by(FacebookPage.page_name.asc())
    ).scalars().all()
    instagram_accounts = db.execute(
        select(InstagramAccount)
        .where(InstagramAccount.company_id == company_id)
        .order_by(InstagramAccount.username.asc().nulls_last(), InstagramAccount.instagram_account_id.asc())
    ).scalars().all()

    return {
        "facebook_pages": [
            {
                "id": str(page.id),
                "page_id": page.page_id,
                "page_name": page.page_name,
                "created_at": page.created_at.isoformat(),
            }
            for page in pages
        ],
        "instagram_accounts": [
            {
                "id": str(account.id),
                "instagram_account_id": account.instagram_account_id,
                "username": account.username,
                "linked_page_id": account.linked_page_id,
                "created_at": account.created_at.isoformat(),
            }
            for account in instagram_accounts
        ],
    }
