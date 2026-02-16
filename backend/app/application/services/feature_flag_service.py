from __future__ import annotations

import json
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.domain.models.feature_flag import FeatureFlag
from app.infrastructure.cache.redis_client import get_redis_client

FLAG_KEYS = [
    ("beta_public_pricing", "Public pricing and checkout flow"),
    ("beta_admin_panel", "Operator dashboard and support tools"),
    ("beta_ai_quality", "AI quality and safety enforcement"),
    ("auto_disable_connector_on_repeated_failures", "Auto-recovery disables unstable connectors"),
    ("auto_throttle_tenant_on_high_error_rate", "Auto-recovery throttles tenants with high error rates"),
    ("enable_global_publish_circuit_breaker", "Global publish pause during incidents"),
    ("enable_tenant_publish_circuit_breaker", "Tenant-level publish pause during incidents"),
    ("maintenance_read_only_mode", "Global read-only maintenance mode"),
    ("enforce_tenant_risk_controls", "Require manual approval when tenant risk is high"),
    ("v1_onboarding_first_value", "Guided first-value onboarding flow"),
    ("v1_auto_project_after_signup", "Automatically create a starter project after signup"),
    ("v1_template_library", "Template library and post-from-template flow"),
    ("v1_smart_tooltips", "Contextual UX tooltips for first-run guidance"),
    ("v1_plan_limit_visualization", "Usage bars and limit-aware UI controls"),
    ("v1_subscription_lifecycle_ux", "Upgrade/downgrade/cancel billing lifecycle experience"),
    ("v1_conversion_nudges", "Conversion-oriented contextual product nudges"),
]


def bootstrap_feature_flags(db: Session) -> None:
    existing_keys = {
        key
        for (key,) in db.execute(select(FeatureFlag.key)).all()
    }
    for key, description in FLAG_KEYS:
        if key in existing_keys:
            continue
        db.add(
            FeatureFlag(
                key=key,
                enabled_globally=False,
                enabled_per_tenant={},
                description=description,
            )
        )


def _cache_key(tenant_id: UUID | None) -> str:
    return f"feature_flags:{str(tenant_id) if tenant_id else 'global'}"


def invalidate_feature_flags_cache(tenant_id: UUID | None = None) -> None:
    redis = get_redis_client()
    if tenant_id is None:
        keys = redis.keys("feature_flags:*")
        if keys:
            redis.delete(*keys)
        return
    redis.delete(_cache_key(tenant_id))


def _serialize_flags(flags: list[FeatureFlag], tenant_id: UUID | None) -> list[dict]:
    tenant_key = str(tenant_id) if tenant_id else ""
    payload: list[dict] = []
    for flag in flags:
        enabled_for_tenant = False
        if tenant_key and isinstance(flag.enabled_per_tenant, dict):
            enabled_for_tenant = bool(flag.enabled_per_tenant.get(tenant_key, False))
        payload.append(
            {
                "id": str(flag.id),
                "key": flag.key,
                "description": flag.description,
                "enabled_globally": bool(flag.enabled_globally),
                "enabled_for_tenant": enabled_for_tenant,
                "effective_enabled": bool(flag.enabled_globally) or enabled_for_tenant,
                "updated_at": flag.updated_at.isoformat(),
            }
        )
    return payload


def list_feature_flags(db: Session, *, tenant_id: UUID | None) -> list[dict]:
    redis = get_redis_client()
    cache_key = _cache_key(tenant_id)
    cached = redis.get(cache_key)
    if cached:
        return json.loads(cached)

    flags = db.execute(select(FeatureFlag).order_by(FeatureFlag.key.asc())).scalars().all()
    payload = _serialize_flags(flags, tenant_id)
    redis.set(cache_key, json.dumps(payload), ex=max(10, settings.feature_flag_cache_ttl_seconds))
    return payload


def is_feature_enabled(db: Session, *, key: str, tenant_id: UUID | None) -> bool:
    flags = list_feature_flags(db, tenant_id=tenant_id)
    for flag in flags:
        if flag["key"] == key:
            return bool(flag["effective_enabled"])
    return False
