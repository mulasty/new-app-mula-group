from uuid import UUID

import hmac
import json
from hashlib import sha256

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.services.audit_service import log_audit_event
from app.application.services.connector_credentials_service import (
    get_connector_credential,
    mark_connector_credential_error,
    revoke_connector_credential,
    upsert_connector_credential,
)
from app.application.services.connector_ops_service import (
    calculate_connector_health,
    clear_connector_sandbox_mode,
    get_connector_backoff_ttl,
    set_connector_sandbox_mode,
)
from app.application.services.feature_flag_service import is_feature_enabled
from app.core.config import settings
from app.domain.models.channel import Channel
from app.domain.models.publish_event import PublishEvent
from app.domain.models.user import User, UserRole
from app.integrations.channel_adapters import AdapterAuthError, get_channel_adapter
from app.integrations.channel_adapters import get_adapter_capabilities, list_registered_adapter_types
from app.interfaces.api.deps import get_current_user, require_roles, require_tenant_id
from app.infrastructure.cache.redis_client import get_redis_client
from app.infrastructure.db.session import get_db

router = APIRouter(prefix="/connectors", tags=["connectors"])


DISPLAY_NAMES = {
    "website": "Website",
    "linkedin": "LinkedIn",
    "facebook": "Facebook",
    "instagram": "Instagram",
    "tiktok": "TikTok",
    "threads": "Threads",
    "x": "X / Twitter",
    "pinterest": "Pinterest",
    "youtube": "YouTube",
}

OAUTH_PATHS = {
    "linkedin": "/channels/linkedin/oauth/start",
    "facebook": "/channels/meta/oauth/start",
    "instagram": "/channels/meta/oauth/start",
    "tiktok": "/channels/tiktok/oauth/start",
    "threads": "/channels/threads/oauth/start",
    "x": "/channels/x/oauth/start",
    "pinterest": "/channels/pinterest/oauth/start",
}

KNOWN_PLATFORMS = [
    "linkedin",
    "facebook",
    "instagram",
    "tiktok",
    "threads",
    "x",
    "pinterest",
    "youtube",
    "website",
]


@router.get("/available", status_code=status.HTTP_200_OK)
def list_available_connectors(
    db: Session = Depends(get_db),
    tenant_id: UUID = Depends(require_tenant_id),
    current_user: User = Depends(get_current_user),
) -> dict:
    discovered = set(list_registered_adapter_types())
    platforms = [*KNOWN_PLATFORMS]
    for discovered_platform in sorted(discovered):
        if discovered_platform not in platforms:
            platforms.append(discovered_platform)
    items = []
    for platform in platforms:
        available = platform in discovered
        capabilities = get_adapter_capabilities(platform) if available else {}
        credential = get_connector_credential(db, tenant_id=tenant_id, connector_type=platform)
        last_status = db.execute(
            select(PublishEvent.status)
            .where(
                PublishEvent.company_id == tenant_id,
                PublishEvent.event_type.in_(["ChannelPublishSucceeded", "ChannelPublishFailed"]),
                PublishEvent.metadata_json["channel_type"].astext == platform,
            )
            .order_by(PublishEvent.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        items.append(
            {
                "platform": platform,
                "display_name": DISPLAY_NAMES.get(platform, platform.title()),
                "capabilities": capabilities,
                "oauth_start_path": OAUTH_PATHS.get(platform),
                "available": available,
                "credential_status": (credential.status if credential else "missing"),
                "token_expires_at": credential.expires_at.isoformat() if credential and credential.expires_at else None,
                "last_error": credential.last_error if credential else None,
                "last_publish_status": last_status,
            }
        )
    return {"items": items}


@router.get("/{connector_id}/health", status_code=status.HTTP_200_OK)
def connector_health(
    connector_id: UUID,
    db: Session = Depends(get_db),
    tenant_id: UUID = Depends(require_tenant_id),
    current_user: User = Depends(get_current_user),
) -> dict:
    if not is_feature_enabled(db, key="v1_connector_hardening", tenant_id=tenant_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector hardening disabled")
    return calculate_connector_health(db, tenant_id=tenant_id, channel_id=connector_id)


@router.post("/{connector_id}/disconnect", status_code=status.HTTP_200_OK)
def disconnect_connector(
    connector_id: UUID,
    db: Session = Depends(get_db),
    tenant_id: UUID = Depends(require_tenant_id),
    current_user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN)),
) -> dict:
    if not is_feature_enabled(db, key="v1_connector_hardening", tenant_id=tenant_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector hardening disabled")
    channel = db.execute(
        select(Channel).where(Channel.id == connector_id, Channel.company_id == tenant_id)
    ).scalar_one_or_none()
    if channel is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector not found")
    channel.status = "disabled"
    revoke_connector_credential(db, tenant_id=tenant_id, connector_type=channel.type)
    clear_connector_sandbox_mode(connector_id)
    log_audit_event(
        db,
        company_id=tenant_id,
        action="connector.disconnected",
        metadata={"channel_id": str(channel.id), "channel_type": channel.type, "user_id": str(current_user.id)},
    )
    db.add(channel)
    db.commit()
    return {"updated": True, "status": channel.status}


@router.post("/{connector_id}/refresh-token", status_code=status.HTTP_200_OK)
async def refresh_connector_token(
    connector_id: UUID,
    db: Session = Depends(get_db),
    tenant_id: UUID = Depends(require_tenant_id),
    current_user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN)),
) -> dict:
    if not is_feature_enabled(db, key="v1_connector_hardening", tenant_id=tenant_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector hardening disabled")
    channel = db.execute(
        select(Channel).where(Channel.id == connector_id, Channel.company_id == tenant_id)
    ).scalar_one_or_none()
    if channel is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector not found")
    adapter = get_channel_adapter(channel.type, db, strict=False)
    try:
        await adapter.refresh_credentials()
        credential = get_connector_credential(db, tenant_id=tenant_id, connector_type=channel.type)
        if credential is not None:
            credential.status = "active"
            credential.last_error = None
            db.add(credential)
        db.commit()
        return {"updated": True, "status": "active"}
    except AdapterAuthError as exc:
        mark_connector_credential_error(
            db,
            tenant_id=tenant_id,
            connector_type=channel.type,
            message=str(exc),
            status="revoked",
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/{connector_id}/test-publish", status_code=status.HTTP_200_OK)
def connector_test_publish(
    connector_id: UUID,
    scenario: str = "simulate_success",
    ttl_seconds: int = 900,
    db: Session = Depends(get_db),
    tenant_id: UUID = Depends(require_tenant_id),
    current_user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN)),
) -> dict:
    if not is_feature_enabled(db, key="v1_connector_sandbox_mode", tenant_id=tenant_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector sandbox disabled")
    channel = db.execute(
        select(Channel).where(Channel.id == connector_id, Channel.company_id == tenant_id)
    ).scalar_one_or_none()
    if channel is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector not found")
    set_connector_sandbox_mode(connector_id, scenario=scenario, ttl_seconds=ttl_seconds)
    log_audit_event(
        db,
        company_id=tenant_id,
        action="connector.test_publish_configured",
        metadata={"channel_id": str(channel.id), "scenario": scenario, "user_id": str(current_user.id)},
    )
    db.commit()
    return {"updated": True, "scenario": scenario, "ttl_seconds": ttl_seconds}


@router.get("/{connector_id}/cooldown", status_code=status.HTTP_200_OK)
def connector_cooldown(
    connector_id: UUID,
    db: Session = Depends(get_db),
    tenant_id: UUID = Depends(require_tenant_id),
    current_user: User = Depends(get_current_user),
) -> dict:
    if not is_feature_enabled(db, key="v1_connector_hardening", tenant_id=tenant_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector hardening disabled")
    channel = db.execute(
        select(Channel).where(Channel.id == connector_id, Channel.company_id == tenant_id)
    ).scalar_one_or_none()
    if channel is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector not found")
    return {"connector_id": str(connector_id), "backoff_seconds": get_connector_backoff_ttl(connector_id)}


@router.post("/webhooks/{provider}", status_code=status.HTTP_202_ACCEPTED)
async def provider_webhook(
    provider: str,
    request: Request,
    x_signature: str | None = Header(default=None, alias="X-Signature"),
    db: Session = Depends(get_db),
) -> dict:
    if not is_feature_enabled(db, key="v1_connector_webhooks", tenant_id=None):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector webhooks disabled")
    body = await request.body()
    provider_key = provider.strip().lower()
    secret = {
        "meta": settings.meta_webhook_app_secret,
        "facebook": settings.meta_webhook_app_secret,
        "instagram": settings.meta_webhook_app_secret,
        "tiktok": settings.tiktok_webhook_secret,
        "x": settings.x_webhook_secret,
        "pinterest": settings.pinterest_webhook_secret,
    }.get(provider_key)
    if secret and x_signature:
        computed = hmac.new(secret.encode("utf-8"), body, sha256).hexdigest()
        if not hmac.compare_digest(computed, x_signature):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid webhook signature")

    try:
        payload = json.loads(body.decode("utf-8")) if body else {}
    except Exception:
        payload = {}
    event_id = str(payload.get("id") or payload.get("event_id") or "")
    redis = get_redis_client()
    if event_id:
        key = f"webhook_dedupe:{provider_key}:{event_id}"
        if not redis.set(key, "1", nx=True, ex=3600):
            return {"accepted": True, "deduplicated": True}

    tenant_raw = payload.get("company_id") or payload.get("tenant_id")
    if tenant_raw:
        try:
            tenant_id = UUID(str(tenant_raw))
            log_audit_event(
                db,
                company_id=tenant_id,
                action="connector.webhook.received",
                metadata={"provider": provider_key, "event_id": event_id or None},
            )
        except Exception:
            pass
    db.commit()
    return {"accepted": True, "provider": provider_key, "event_id": event_id or None}
