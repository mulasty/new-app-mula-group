from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from statistics import mean
from time import perf_counter
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.application.services.audit_service import log_audit_event
from app.application.services.feature_flag_service import is_feature_enabled
from app.core.config import settings
from app.domain.models.channel import Channel
from app.domain.models.company import Company
from app.domain.models.company_subscription import CompanySubscription
from app.domain.models.company_usage import CompanyUsage
from app.domain.models.content_item import ContentItem
from app.domain.models.performance_baseline import PerformanceBaseline
from app.domain.models.platform_incident import PlatformIncident
from app.domain.models.post import Post
from app.domain.models.publish_event import PublishEvent
from app.domain.models.revenue_metric import RevenueMetric
from app.domain.models.subscription_plan import SubscriptionPlan
from app.domain.models.system_health import SystemHealth
from app.domain.models.tenant_risk_score import TenantRiskScore
from app.infrastructure.cache.redis_client import get_redis_client


AUTO_THROTTLE_TTL_SECONDS = 15 * 60
TENANT_RISK_THRESHOLD = settings.tenant_risk_manual_approval_threshold


@dataclass(frozen=True)
class SystemHealthScore:
    score: int
    components: list[dict]
    publish_failure_rate: float
    db_latency_ms: float
    redis_latency_ms: float
    worker_backlog_size: int
    request_latency_ms: float


def _upsert_system_health(
    db: Session,
    *,
    component: str,
    status: str,
    latency_ms: float,
    error_rate: float,
) -> None:
    existing = db.execute(select(SystemHealth).where(SystemHealth.component == component)).scalar_one_or_none()
    if existing is None:
        existing = SystemHealth(component=component)
    existing.status = status
    existing.latency_ms = float(max(0.0, latency_ms))
    existing.error_rate = float(max(0.0, error_rate))
    existing.updated_at = datetime.now(UTC)
    db.add(existing)


def _worker_backlog_size() -> int:
    redis = get_redis_client()
    try:
        return sum(int(redis.llen(queue_name) or 0) for queue_name in ("publishing", "scheduler", "analytics"))
    except Exception:
        return 0


def _request_latency_ms_sample() -> float:
    redis = get_redis_client()
    try:
        raw = redis.get("platform:perf:request_latency_ms:avg")
        if raw is None:
            return 0.0
        return float(raw)
    except Exception:
        return 0.0


def _publish_failure_rate(db: Session, *, window_minutes: int = 60) -> float:
    since = datetime.now(UTC) - timedelta(minutes=window_minutes)
    attempts = db.execute(
        select(func.count(PublishEvent.id)).where(
            PublishEvent.created_at >= since,
            PublishEvent.event_type.in_(["ChannelPublishSucceeded", "ChannelPublishFailed"]),
        )
    ).scalar_one()
    failures = db.execute(
        select(func.count(PublishEvent.id)).where(
            PublishEvent.created_at >= since,
            PublishEvent.event_type == "ChannelPublishFailed",
        )
    ).scalar_one()
    attempts_value = float(attempts or 0)
    failures_value = float(failures or 0)
    if attempts_value <= 0:
        return 0.0
    return failures_value / attempts_value


def _db_latency_ms(db: Session) -> float:
    started = perf_counter()
    db.execute(text("SELECT 1"))
    return round((perf_counter() - started) * 1000, 3)


def _redis_latency_ms() -> float:
    redis = get_redis_client()
    started = perf_counter()
    redis.ping()
    return round((perf_counter() - started) * 1000, 3)


def _status_for_threshold(value: float, warning: float, critical: float) -> str:
    if value >= critical:
        return "critical"
    if value >= warning:
        return "warning"
    return "ok"


def calculate_system_health_score(db: Session) -> SystemHealthScore:
    publish_failure_rate = _publish_failure_rate(db)
    db_latency_ms = _db_latency_ms(db)
    redis_latency_ms = _redis_latency_ms()
    worker_backlog_size = _worker_backlog_size()
    request_latency_ms = _request_latency_ms_sample()

    _upsert_system_health(
        db,
        component="publishing",
        status=_status_for_threshold(
            publish_failure_rate * 100,
            settings.system_publish_failure_alert_threshold * 100,
            (settings.system_publish_failure_alert_threshold * 100) * 2,
        ),
        latency_ms=0.0,
        error_rate=publish_failure_rate,
    )
    _upsert_system_health(
        db,
        component="database",
        status=_status_for_threshold(
            db_latency_ms,
            float(settings.system_db_latency_alert_ms),
            float(settings.system_db_latency_alert_ms * 2),
        ),
        latency_ms=db_latency_ms,
        error_rate=0.0,
    )
    _upsert_system_health(
        db,
        component="redis",
        status=_status_for_threshold(redis_latency_ms, 40, 100),
        latency_ms=redis_latency_ms,
        error_rate=0.0,
    )
    _upsert_system_health(
        db,
        component="worker_backlog",
        status=_status_for_threshold(
            float(worker_backlog_size),
            float(settings.system_worker_backlog_alert_threshold),
            float(settings.system_worker_backlog_alert_threshold * 3),
        ),
        latency_ms=0.0,
        error_rate=0.0,
    )
    _upsert_system_health(
        db,
        component="api_requests",
        status=_status_for_threshold(request_latency_ms, 250, 700),
        latency_ms=request_latency_ms,
        error_rate=0.0,
    )
    db.flush()

    penalties = [
        min(35.0, publish_failure_rate * 400.0),
        min(25.0, max(0.0, db_latency_ms - 80.0) / 8.0),
        min(15.0, max(0.0, redis_latency_ms - 20.0) / 5.0),
        min(15.0, worker_backlog_size / 20.0),
        min(10.0, max(0.0, request_latency_ms - 120.0) / 20.0),
    ]
    score = int(max(0.0, min(100.0, 100.0 - sum(penalties))))
    components = db.execute(select(SystemHealth).order_by(SystemHealth.component.asc())).scalars().all()
    return SystemHealthScore(
        score=score,
        components=[
            {
                "component": item.component,
                "status": item.status,
                "latency_ms": item.latency_ms,
                "error_rate": item.error_rate,
                "updated_at": item.updated_at.isoformat(),
            }
            for item in components
        ],
        publish_failure_rate=publish_failure_rate,
        db_latency_ms=db_latency_ms,
        redis_latency_ms=redis_latency_ms,
        worker_backlog_size=worker_backlog_size,
        request_latency_ms=request_latency_ms,
    )


def create_incident(
    db: Session,
    *,
    incident_type: str,
    message: str,
    severity: str = "warning",
    company_id: UUID | None = None,
    metadata_json: dict | None = None,
) -> PlatformIncident:
    incident = PlatformIncident(
        company_id=company_id,
        incident_type=incident_type,
        severity=severity,
        status="open",
        message=message,
        metadata_json=metadata_json or {},
    )
    db.add(incident)
    return incident


def resolve_incident(db: Session, *, incident_id: UUID, resolved_by: str) -> PlatformIncident | None:
    incident = db.execute(select(PlatformIncident).where(PlatformIncident.id == incident_id)).scalar_one_or_none()
    if incident is None:
        return None
    incident.status = "resolved"
    incident.resolved_at = datetime.now(UTC)
    incident.metadata_json = {**(incident.metadata_json or {}), "resolved_by": resolved_by}
    db.add(incident)
    return incident


def _tenant_publish_failure_ratio(db: Session, company_id: UUID, window_days: int = 7) -> float:
    since = datetime.now(UTC) - timedelta(days=window_days)
    attempts = db.execute(
        select(func.count(PublishEvent.id)).where(
            PublishEvent.company_id == company_id,
            PublishEvent.created_at >= since,
            PublishEvent.event_type.in_(["ChannelPublishSucceeded", "ChannelPublishFailed"]),
        )
    ).scalar_one()
    failures = db.execute(
        select(func.count(PublishEvent.id)).where(
            PublishEvent.company_id == company_id,
            PublishEvent.created_at >= since,
            PublishEvent.event_type == "ChannelPublishFailed",
        )
    ).scalar_one()
    attempts_value = float(attempts or 0)
    if attempts_value <= 0:
        return 0.0
    return float(failures or 0) / attempts_value


def _tenant_flagged_content_ratio(db: Session, company_id: UUID, window_days: int = 30) -> float:
    since = datetime.now(UTC) - timedelta(days=window_days)
    ai_items = db.execute(
        select(ContentItem).where(ContentItem.company_id == company_id, ContentItem.created_at >= since)
    ).scalars().all()
    if not ai_items:
        return 0.0
    flagged = 0
    for item in ai_items:
        quality = (item.metadata_json or {}).get("quality", {})
        risk_score = float(quality.get("risk_score", 0.0) or 0.0) if isinstance(quality, dict) else 0.0
        if item.status == "needs_review" or risk_score >= 0.65:
            flagged += 1
    return flagged / len(ai_items)


def _tenant_rate_limit_violations(company_id: UUID) -> int:
    redis = get_redis_client()
    try:
        return int(redis.get(f"tenant:rate_limit_violations:{company_id}") or 0)
    except Exception:
        return 0


def calculate_tenant_risk_score(db: Session, *, company_id: UUID) -> dict:
    publish_failure_ratio = _tenant_publish_failure_ratio(db, company_id)
    flagged_content_ratio = _tenant_flagged_content_ratio(db, company_id)
    rate_limit_violations = _tenant_rate_limit_violations(company_id)
    abuse_rate = min(1.0, rate_limit_violations / 100.0)

    score_value = int(
        min(
            100,
            round(
                (publish_failure_ratio * 45.0)
                + (flagged_content_ratio * 30.0)
                + (abuse_rate * 25.0)
            ),
        )
    )
    risk_level = "low"
    if score_value >= 80:
        risk_level = "critical"
    elif score_value >= 60:
        risk_level = "high"
    elif score_value >= 35:
        risk_level = "medium"

    existing = db.execute(
        select(TenantRiskScore).where(TenantRiskScore.company_id == company_id)
    ).scalar_one_or_none()
    if existing is None:
        existing = TenantRiskScore(company_id=company_id)
    existing.risk_score = score_value
    existing.publish_failure_ratio = publish_failure_ratio
    existing.flagged_content_ratio = flagged_content_ratio
    existing.abuse_rate = abuse_rate
    existing.rate_limit_violations = rate_limit_violations
    existing.risk_level = risk_level
    existing.metadata_json = {
        "threshold_manual_approval": TENANT_RISK_THRESHOLD,
        "window_days": 7,
    }
    existing.updated_at = datetime.now(UTC)
    db.add(existing)
    db.flush()
    return {
        "company_id": str(company_id),
        "risk_score": score_value,
        "risk_level": risk_level,
        "publish_failure_ratio": round(publish_failure_ratio, 4),
        "flagged_content_ratio": round(flagged_content_ratio, 4),
        "abuse_rate": round(abuse_rate, 4),
        "rate_limit_violations": rate_limit_violations,
    }


def calculate_revenue_metrics(db: Session, *, company_id: UUID) -> dict:
    subscription = db.execute(
        select(CompanySubscription).where(CompanySubscription.company_id == company_id)
    ).scalar_one_or_none()
    usage = db.execute(select(CompanyUsage).where(CompanyUsage.company_id == company_id)).scalar_one_or_none()
    plan = None
    if subscription is not None:
        plan = db.execute(select(SubscriptionPlan).where(SubscriptionPlan.id == subscription.plan_id)).scalar_one_or_none()

    monthly_price = float(plan.monthly_price) if plan else 0.0
    usage_count = int(usage.posts_used_current_period if usage else 0)
    max_posts = int(plan.max_posts_per_month if plan else 1)
    usage_percent = max(0.0, min(1.0, usage_count / max(1, max_posts)))
    publish_failure_ratio = _tenant_publish_failure_ratio(db, company_id)
    churn_risk_score = max(0.0, min(1.0, ((1.0 - usage_percent) * 0.6) + (publish_failure_ratio * 0.4)))
    upgrade_probability = max(0.0, min(1.0, (usage_percent * 0.75) + (0.2 if usage_percent > 0.85 else 0.0)))
    overuse_detected = usage_percent > 1.0

    row = db.execute(
        select(RevenueMetric).where(RevenueMetric.company_id == company_id)
    ).scalar_one_or_none()
    if row is None:
        row = RevenueMetric(company_id=company_id)
    row.mrr = monthly_price
    row.plan = plan.name if plan else "Starter"
    row.usage_percent = usage_percent
    row.churn_risk_score = churn_risk_score
    row.upgrade_probability = upgrade_probability
    row.overuse_detected = overuse_detected
    row.updated_at = datetime.now(UTC)
    db.add(row)
    db.flush()
    return {
        "company_id": str(company_id),
        "mrr": float(monthly_price),
        "plan": row.plan,
        "usage_percent": round(usage_percent, 4),
        "churn_risk_score": round(churn_risk_score, 4),
        "upgrade_probability": round(upgrade_probability, 4),
        "overuse_detected": overuse_detected,
    }


def calculate_revenue_overview(db: Session) -> dict:
    company_ids = [company_id for (company_id,) in db.execute(select(Company.id)).all()]
    items = [calculate_revenue_metrics(db, company_id=company_id) for company_id in company_ids]
    total_mrr = sum(item["mrr"] for item in items)
    churn_risk_avg = mean(item["churn_risk_score"] for item in items) if items else 0.0
    return {
        "tenants": items,
        "summary": {
            "tenant_count": len(items),
            "total_mrr": round(total_mrr, 2),
            "avg_churn_risk_score": round(churn_risk_avg, 4),
        },
    }


def record_performance_baseline(
    db: Session,
    *,
    component: str,
    metric_name: str,
    samples: list[float],
) -> None:
    if not samples:
        return
    sorted_samples = sorted(samples)
    p95_index = min(len(sorted_samples) - 1, max(0, int(len(sorted_samples) * 0.95) - 1))
    avg_value = float(mean(sorted_samples))
    p95_value = float(sorted_samples[p95_index])

    recent = db.execute(
        select(PerformanceBaseline)
        .where(
            PerformanceBaseline.component == component,
            PerformanceBaseline.metric_name == metric_name,
        )
        .order_by(PerformanceBaseline.recorded_at.desc())
        .limit(5)
    ).scalars().all()
    previous_avg = mean([item.avg_value for item in recent]) if recent else avg_value
    regression_detected = previous_avg > 0 and avg_value > (previous_avg * 1.25)

    db.add(
        PerformanceBaseline(
            component=component,
            metric_name=metric_name,
            avg_value=avg_value,
            p95_value=p95_value,
            sample_size=len(samples),
            regression_detected=regression_detected,
        )
    )


def _fetch_perf_samples(redis_key: str, *, max_items: int = 500) -> list[float]:
    redis = get_redis_client()
    values = redis.lrange(redis_key, 0, max_items - 1)
    samples: list[float] = []
    for value in values:
        try:
            samples.append(float(value))
        except (TypeError, ValueError):
            continue
    return samples


def collect_and_store_performance_baselines(db: Session) -> dict:
    publish_samples = db.execute(
        select(PublishEvent.metadata_json)
        .where(
            PublishEvent.event_type.in_(["ChannelPublishSucceeded", "ChannelPublishFailed"]),
            PublishEvent.created_at >= datetime.now(UTC) - timedelta(hours=4),
        )
        .limit(1000)
    ).scalars().all()
    publish_latency_values: list[float] = []
    for metadata in publish_samples:
        if not isinstance(metadata, dict):
            continue
        value = metadata.get("publish_duration_ms")
        try:
            publish_latency_values.append(float(value))
        except (TypeError, ValueError):
            continue
    record_performance_baseline(
        db,
        component="publishing",
        metric_name="average_publish_latency_ms",
        samples=publish_latency_values,
    )
    record_performance_baseline(
        db,
        component="scheduler",
        metric_name="scheduler_scan_duration_ms",
        samples=_fetch_perf_samples("platform:perf:scheduler_scan_duration_ms"),
    )
    record_performance_baseline(
        db,
        component="analytics",
        metric_name="analytics_query_duration_ms",
        samples=_fetch_perf_samples("platform:perf:analytics_query_duration_ms"),
    )
    record_performance_baseline(
        db,
        component="dashboard",
        metric_name="dashboard_load_time_ms",
        samples=_fetch_perf_samples("platform:perf:dashboard_load_time_ms"),
    )
    return {"stored": True}


def append_perf_sample(metric_name: str, value_ms: float, *, max_samples: int = 500) -> None:
    redis = get_redis_client()
    key = f"platform:perf:{metric_name}"
    redis.lpush(key, f"{float(value_ms):.6f}")
    redis.ltrim(key, 0, max_samples - 1)
    if metric_name == "request_latency_ms":
        values = _fetch_perf_samples(key)
        if values:
            redis.set("platform:perf:request_latency_ms:avg", f"{mean(values):.6f}", ex=300)


def set_global_publish_breaker(enabled: bool, *, reason: str) -> None:
    redis = get_redis_client()
    redis.set("platform:breaker:global_publish", "1" if enabled else "0")
    redis.set("platform:breaker:global_publish:reason", reason, ex=3600)


def set_tenant_publish_breaker(tenant_id: UUID, enabled: bool, *, reason: str) -> None:
    redis = get_redis_client()
    key = f"platform:breaker:tenant:{tenant_id}"
    if enabled:
        redis.set(key, "1", ex=1800)
        redis.set(f"{key}:reason", reason, ex=1800)
    else:
        redis.delete(key)
        redis.delete(f"{key}:reason")


def is_global_publish_paused() -> tuple[bool, str | None]:
    redis = get_redis_client()
    paused = str(redis.get("platform:breaker:global_publish") or "0") == "1"
    reason = redis.get("platform:breaker:global_publish:reason") if paused else None
    return paused, reason


def is_tenant_publish_paused(tenant_id: UUID) -> tuple[bool, str | None]:
    redis = get_redis_client()
    key = f"platform:breaker:tenant:{tenant_id}"
    paused = str(redis.get(key) or "0") == "1"
    reason = redis.get(f"{key}:reason") if paused else None
    return paused, reason


def execute_auto_recovery(db: Session) -> dict:
    redis = get_redis_client()
    actions: list[dict] = []

    # Worker heartbeat recovery signal.
    worker_heartbeat = redis.get(settings.worker_heartbeat_key)
    if not worker_heartbeat:
        incident = create_incident(
            db,
            incident_type="worker_heartbeat_missing",
            message="Worker heartbeat key is missing; automatic restart requested",
            severity="critical",
        )
        actions.append({"action": "worker_restart_event", "incident_id": str(incident.id)})

    # Channel auto-disable on repeated failures.
    if is_feature_enabled(db, key="auto_disable_connector_on_repeated_failures", tenant_id=None):
        since = datetime.now(UTC) - timedelta(hours=1)
        failure_rows = db.execute(
            select(PublishEvent.channel_id, func.count(PublishEvent.id))
            .where(
                PublishEvent.event_type == "ChannelPublishFailed",
                PublishEvent.created_at >= since,
                PublishEvent.channel_id.is_not(None),
            )
            .group_by(PublishEvent.channel_id)
            .having(func.count(PublishEvent.id) >= 5)
        ).all()
        for channel_id, failures in failure_rows:
            channel = db.execute(select(Channel).where(Channel.id == channel_id)).scalar_one_or_none()
            if channel is None or channel.status == "disabled":
                continue
            channel.status = "disabled"
            db.add(channel)
            log_audit_event(
                db,
                company_id=channel.company_id,
                action="auto_recovery.connector_disabled",
                metadata={"channel_id": str(channel.id), "failures": int(failures or 0)},
            )
            create_incident(
                db,
                company_id=channel.company_id,
                incident_type="connector_disabled_repeated_failures",
                severity="warning",
                message=f"Channel {channel.id} disabled after repeated failures",
                metadata_json={"failures": int(failures or 0)},
            )
            actions.append({"action": "connector_disabled", "channel_id": str(channel.id)})

    # Tenant temporary throttling.
    if is_feature_enabled(db, key="auto_throttle_tenant_on_high_error_rate", tenant_id=None):
        tenants = [tenant_id for (tenant_id,) in db.execute(select(Company.id)).all()]
        for tenant_id in tenants:
            risk = calculate_tenant_risk_score(db, company_id=tenant_id)
            if risk["risk_score"] >= TENANT_RISK_THRESHOLD:
                throttle_key = f"tenant:throttle:{tenant_id}"
                redis.set(throttle_key, "1", ex=AUTO_THROTTLE_TTL_SECONDS)
                log_audit_event(
                    db,
                    company_id=tenant_id,
                    action="auto_recovery.tenant_throttled",
                    metadata={"risk_score": risk["risk_score"], "ttl_seconds": AUTO_THROTTLE_TTL_SECONDS},
                )
                actions.append({"action": "tenant_throttled", "tenant_id": str(tenant_id)})
                if is_feature_enabled(db, key="enable_tenant_publish_circuit_breaker", tenant_id=tenant_id):
                    set_tenant_publish_breaker(
                        tenant_id,
                        True,
                        reason="Automatic tenant publish breaker enabled by risk controls",
                    )
                    actions.append({"action": "tenant_publish_breaker_enabled", "tenant_id": str(tenant_id)})
    return {"actions": actions}


def evaluate_platform_guardrails(db: Session, *, health: SystemHealthScore) -> dict:
    actions: list[dict] = []
    if health.publish_failure_rate > 0.08 and is_feature_enabled(db, key="enable_global_publish_circuit_breaker", tenant_id=None):
        set_global_publish_breaker(True, reason="Automatic global pause due to elevated publish failures")
        create_incident(
            db,
            incident_type="global_publish_breaker_enabled",
            severity="critical",
            message="Publishing paused globally due to elevated failure rate",
            metadata_json={"publish_failure_rate": round(health.publish_failure_rate, 4)},
        )
        actions.append({"action": "global_breaker_enabled"})
    return {"actions": actions}


def get_active_incidents(db: Session, *, limit: int = 100) -> list[dict]:
    incidents = db.execute(
        select(PlatformIncident)
        .where(PlatformIncident.status == "open")
        .order_by(PlatformIncident.created_at.desc())
        .limit(limit)
    ).scalars().all()
    return [
        {
            "id": str(item.id),
            "company_id": str(item.company_id) if item.company_id else None,
            "incident_type": item.incident_type,
            "severity": item.severity,
            "status": item.status,
            "message": item.message,
            "metadata_json": item.metadata_json or {},
            "created_at": item.created_at.isoformat(),
            "resolved_at": item.resolved_at.isoformat() if item.resolved_at else None,
        }
        for item in incidents
    ]
