from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.domain.models.channel import Channel
from app.domain.models.connector_credential import ConnectorCredential
from app.domain.models.publish_event import PublishEvent
from app.infrastructure.cache.redis_client import get_redis_client

CONNECTOR_BACKOFF_PREFIX = "connector_backoff"
CONNECTOR_COOLDOWN_PREFIX = "connector_health_cooldown"
CONNECTOR_SANDBOX_PREFIX = "connector_sandbox"


def _backoff_key(channel_id: UUID) -> str:
    return f"{CONNECTOR_BACKOFF_PREFIX}:{channel_id}"


def _cooldown_key(channel_id: UUID) -> str:
    return f"{CONNECTOR_COOLDOWN_PREFIX}:{channel_id}"


def _sandbox_key(channel_id: UUID) -> str:
    return f"{CONNECTOR_SANDBOX_PREFIX}:{channel_id}"


def set_connector_backoff(channel_id: UUID, *, seconds: int) -> None:
    redis_client = get_redis_client()
    redis_client.setex(_backoff_key(channel_id), max(1, seconds), "1")


def get_connector_backoff_ttl(channel_id: UUID) -> int:
    redis_client = get_redis_client()
    ttl = redis_client.ttl(_backoff_key(channel_id))
    return max(0, int(ttl if ttl and ttl > 0 else 0))


def set_connector_cooldown(channel_id: UUID, *, seconds: int) -> None:
    redis_client = get_redis_client()
    redis_client.setex(_cooldown_key(channel_id), max(1, seconds), "1")


def get_connector_cooldown_ttl(channel_id: UUID) -> int:
    redis_client = get_redis_client()
    ttl = redis_client.ttl(_cooldown_key(channel_id))
    return max(0, int(ttl if ttl and ttl > 0 else 0))


def set_connector_sandbox_mode(channel_id: UUID, *, scenario: str, ttl_seconds: int = 900) -> None:
    redis_client = get_redis_client()
    redis_client.setex(_sandbox_key(channel_id), max(30, ttl_seconds), scenario.strip().lower())


def get_connector_sandbox_mode(channel_id: UUID) -> str | None:
    redis_client = get_redis_client()
    value = redis_client.get(_sandbox_key(channel_id))
    if not value:
        return None
    return str(value).strip().lower()


def clear_connector_sandbox_mode(channel_id: UUID) -> None:
    redis_client = get_redis_client()
    redis_client.delete(_sandbox_key(channel_id))


def calculate_connector_health(db: Session, *, tenant_id: UUID, channel_id: UUID) -> dict:
    channel = db.execute(
        select(Channel).where(Channel.id == channel_id, Channel.company_id == tenant_id)
    ).scalar_one_or_none()
    if channel is None:
        return {"score": 0, "status": "missing"}

    credential = db.execute(
        select(ConnectorCredential).where(
            ConnectorCredential.tenant_id == tenant_id,
            ConnectorCredential.connector_type == channel.type,
        )
    ).scalar_one_or_none()

    recent_q = db.execute(
        select(
            func.count(PublishEvent.id),
            func.sum(case((PublishEvent.status == "ok", 1), else_=0)),
            func.sum(case((PublishEvent.status == "error", 1), else_=0)),
            func.sum(
                case(
                    (PublishEvent.metadata_json["normalized_error"]["category"].astext == "rate_limit", 1),
                    else_=0,
                )
            ),
        ).where(
            PublishEvent.company_id == tenant_id,
            PublishEvent.channel_id == channel_id,
            PublishEvent.event_type.in_(["ChannelPublishSucceeded", "ChannelPublishFailed"]),
        )
    ).one()

    total = int(recent_q[0] or 0)
    success = int(recent_q[1] or 0)
    failed = int(recent_q[2] or 0)
    rate_limited = int(recent_q[3] or 0)
    success_ratio = (success / total) if total else 1.0
    failure_ratio = (failed / total) if total else 0.0
    rate_limit_ratio = (rate_limited / total) if total else 0.0

    token_ok = bool(credential and credential.status == "active")
    token_valid_factor = 1.0 if token_ok else 0.4

    score = int(
        max(
            0.0,
            min(
                100.0,
                (success_ratio * 65.0)
                + ((1.0 - rate_limit_ratio) * 20.0)
                + (token_valid_factor * 15.0),
            ),
        )
    )

    return {
        "channel_id": str(channel.id),
        "connector_type": channel.type,
        "score": score,
        "success_ratio": round(success_ratio, 4),
        "failure_ratio": round(failure_ratio, 4),
        "rate_limit_ratio": round(rate_limit_ratio, 4),
        "token_status": (credential.status if credential else "missing"),
        "token_expires_at": credential.expires_at.isoformat() if credential and credential.expires_at else None,
        "last_error": credential.last_error if credential else None,
        "cooldown_seconds": get_connector_cooldown_ttl(channel.id),
        "backoff_seconds": get_connector_backoff_ttl(channel.id),
    }


def maybe_trip_connector_circuit_breaker(
    db: Session,
    *,
    tenant_id: UUID,
    channel_id: UUID,
    consecutive_failures_threshold: int,
) -> bool:
    channel = db.execute(
        select(Channel).where(Channel.id == channel_id, Channel.company_id == tenant_id)
    ).scalar_one_or_none()
    if channel is None:
        return False

    rows = db.execute(
        select(PublishEvent.status)
        .where(
            PublishEvent.company_id == tenant_id,
            PublishEvent.channel_id == channel_id,
            PublishEvent.event_type.in_(["ChannelPublishSucceeded", "ChannelPublishFailed"]),
        )
        .order_by(PublishEvent.created_at.desc())
        .limit(max(1, consecutive_failures_threshold))
    ).scalars().all()
    if len(rows) < consecutive_failures_threshold:
        return False
    if any(value == "ok" for value in rows):
        return False

    channel.status = "disabled"
    db.add(channel)
    return True


def mark_connector_reenabled(db: Session, *, tenant_id: UUID, channel_id: UUID) -> None:
    channel = db.execute(
        select(Channel).where(Channel.id == channel_id, Channel.company_id == tenant_id)
    ).scalar_one_or_none()
    if channel is None:
        return
    channel.status = "active"
    db.add(channel)
