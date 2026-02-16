import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from time import perf_counter
from uuid import UUID, uuid4

from celery.exceptions import MaxRetriesExceededError
from sqlalchemy import func, select

from app.application.services.publishing_service import emit_publish_event, get_active_channels, publish_post_async
from app.application.services.automation_service import (
    dispatch_due_time_rules,
    dispatch_event_triggered_rules,
    emit_automation_event,
    execute_automation_run_runtime,
)
from app.application.services.audit_service import log_audit_event
from app.application.services.billing_service import reset_monthly_post_usage as reset_monthly_post_usage_service
from app.application.services.platform_ops_service import (
    append_perf_sample,
    calculate_revenue_overview,
    calculate_system_health_score,
    calculate_tenant_risk_score,
    collect_and_store_performance_baselines,
    create_incident,
    evaluate_platform_guardrails,
    execute_auto_recovery,
)
from app.domain.models.automation_run import AutomationRun, AutomationRunStatus
from app.domain.models.channel import Channel
from app.domain.models.channel_publication import ChannelPublication
from app.domain.models.channel_retry_policy import ChannelRetryPolicy, RetryBackoffStrategy
from app.domain.models.failed_job import FailedJob
from app.domain.models.post import Post, PostStatus
from app.domain.models.performance_baseline import PerformanceBaseline
from app.domain.models.publish_event import PublishEvent
from app.core.config import settings
from app.integrations.channel_adapters import (
    AdapterAuthError,
    AdapterPermanentError,
    AdapterRetryableError,
    get_channel_adapter,
)
from app.integrations.platform_rate_limit_service import check_platform_rate_limit
from app.infrastructure.cache.redis_client import get_redis_client
from app.infrastructure.db.session import SessionLocal
from app.infrastructure.observability.metrics import (
    PUBLISH_ATTEMPTS_TOTAL,
    PUBLISH_FAILURES_TOTAL,
    SCHEDULED_JOBS_CHECKED_TOTAL,
    increment_background_counter,
    measure_redis,
)
from workers.celery_app import celery_app

logger = logging.getLogger(__name__)

DEFAULT_MAX_ATTEMPTS = 5
DEFAULT_BACKOFF_STRATEGY = RetryBackoffStrategy.EXPONENTIAL.value
DEFAULT_RETRY_DELAY_SECONDS = 30
MAX_TASK_RETRIES = 5
MAX_CONCURRENT_CHANNEL_PUBLISHES = 5
AUTOMATION_MAX_RETRIES = 5
PUBLISH_LOCK_TTL_SECONDS = 60


@dataclass(frozen=True)
class RetryPolicyConfig:
    max_attempts: int
    backoff_strategy: str
    retry_delay_seconds: int


@dataclass(frozen=True)
class ChannelPublishResult:
    channel_id: UUID
    channel_type: str
    adapter_type: str
    success: bool
    retryable: bool
    publish_duration_ms: int
    metadata: dict
    error: str | None = None


def _record_failed_job(db, *, job_type: str, payload: dict, error_message: str) -> None:
    db.add(
        FailedJob(
            job_type=job_type,
            payload=payload,
            error_message=error_message,
        )
    )


def _get_existing_channel_publication(
    db,
    *,
    company_id: UUID,
    post_id: UUID,
    channel_id: UUID,
) -> ChannelPublication | None:
    return db.execute(
        select(ChannelPublication).where(
            ChannelPublication.company_id == company_id,
            ChannelPublication.post_id == post_id,
            ChannelPublication.channel_id == channel_id,
        )
    ).scalar_one_or_none()


def _default_retry_policy() -> RetryPolicyConfig:
    return RetryPolicyConfig(
        max_attempts=DEFAULT_MAX_ATTEMPTS,
        backoff_strategy=DEFAULT_BACKOFF_STRATEGY,
        retry_delay_seconds=DEFAULT_RETRY_DELAY_SECONDS,
    )


def _normalize_retry_policy(policy: ChannelRetryPolicy | None) -> RetryPolicyConfig:
    if policy is None:
        return _default_retry_policy()
    return RetryPolicyConfig(
        max_attempts=max(1, int(policy.max_attempts)),
        backoff_strategy=policy.backoff_strategy
        if policy.backoff_strategy in {RetryBackoffStrategy.LINEAR.value, RetryBackoffStrategy.EXPONENTIAL.value}
        else DEFAULT_BACKOFF_STRATEGY,
        retry_delay_seconds=max(1, int(policy.retry_delay_seconds)),
    )


def _load_retry_policies(db, channel_types: set[str]) -> dict[str, RetryPolicyConfig]:
    if not channel_types:
        return {}
    rows = db.execute(
        select(ChannelRetryPolicy).where(ChannelRetryPolicy.channel_type.in_(channel_types))
    ).scalars().all()
    policies = {row.channel_type: _normalize_retry_policy(row) for row in rows}
    for channel_type in channel_types:
        policies.setdefault(channel_type, _default_retry_policy())
    return policies


def _compute_retry_delay_seconds(policy: RetryPolicyConfig, attempt: int) -> int:
    normalized_attempt = max(1, attempt)
    if policy.backoff_strategy == RetryBackoffStrategy.LINEAR.value:
        return policy.retry_delay_seconds * normalized_attempt
    return policy.retry_delay_seconds * (2 ** (normalized_attempt - 1))


def _acquire_publish_lock(redis_client, *, post_id: UUID) -> str | None:
    lock_key = f"lock:publish:{post_id}"
    token = str(uuid4())
    with measure_redis("publish_lock_acquire"):
        acquired = redis_client.set(lock_key, token, nx=True, ex=PUBLISH_LOCK_TTL_SECONDS)
    if not acquired:
        return None
    return token


def _release_publish_lock(redis_client, *, post_id: UUID, token: str) -> None:
    lock_key = f"lock:publish:{post_id}"
    try:
        with measure_redis("publish_lock_release"):
            redis_client.eval(
                """
                if redis.call("get", KEYS[1]) == ARGV[1] then
                    return redis.call("del", KEYS[1])
                else
                    return 0
                end
                """,
                1,
                lock_key,
                token,
            )
    except Exception:
        logger.exception("publish_lock_release_failed post_id=%s", post_id)


async def _publish_channel(
    *,
    company_id: UUID,
    post_id: UUID,
    channel_id: UUID,
    attempt: int,
    policy: RetryPolicyConfig,
    semaphore: asyncio.Semaphore,
) -> ChannelPublishResult:
    async with semaphore:
        started_at = perf_counter()
        with SessionLocal() as db:
            post = db.execute(
                select(Post).where(Post.id == post_id, Post.company_id == company_id)
            ).scalar_one_or_none()
            channel = db.execute(
                select(Channel).where(
                    Channel.id == channel_id,
                    Channel.company_id == company_id,
                )
            ).scalar_one_or_none()

            if post is None or channel is None:
                duration_ms = int((perf_counter() - started_at) * 1000)
                return ChannelPublishResult(
                    channel_id=channel_id,
                    channel_type=(channel.type if channel is not None else "unknown"),
                    adapter_type="missing",
                    success=False,
                    retryable=False,
                    publish_duration_ms=duration_ms,
                    metadata={"reason": "post_or_channel_not_found"},
                    error="Post or channel not found for tenant",
                )

            if channel.status != "active":
                duration_ms = int((perf_counter() - started_at) * 1000)
                return ChannelPublishResult(
                    channel_id=channel.id,
                    channel_type=channel.type,
                    adapter_type="inactive",
                    success=False,
                    retryable=False,
                    publish_duration_ms=duration_ms,
                    metadata={"reason": "channel_disabled"},
                    error="Channel is disabled",
                )

            if attempt > policy.max_attempts:
                duration_ms = int((perf_counter() - started_at) * 1000)
                return ChannelPublishResult(
                    channel_id=channel.id,
                    channel_type=channel.type,
                    adapter_type="policy",
                    success=False,
                    retryable=False,
                    publish_duration_ms=duration_ms,
                    metadata={"reason": "retry_policy_exhausted", "max_attempts": policy.max_attempts},
                    error=f"Retry policy exhausted for channel type '{channel.type}'",
                )

            rate_limit_result = check_platform_rate_limit(
                db=db,
                redis_client=get_redis_client(),
                platform=channel.type,
            )
            if not rate_limit_result.allowed:
                duration_ms = int((perf_counter() - started_at) * 1000)
                return ChannelPublishResult(
                    channel_id=channel.id,
                    channel_type=channel.type,
                    adapter_type="rate_limit_guard",
                    success=False,
                    retryable=True,
                    publish_duration_ms=duration_ms,
                    metadata={
                        "error_code": "platform_rate_limited",
                        "platform": rate_limit_result.platform,
                        "rate_limit": rate_limit_result.limit,
                        "rate_limit_current": rate_limit_result.current,
                        "retry_after_seconds": rate_limit_result.retry_after_seconds,
                    },
                    error=(
                        "Platform rate limit exceeded for "
                        f"{rate_limit_result.platform}. Retry after {rate_limit_result.retry_after_seconds}s"
                    ),
                )

            adapter = get_channel_adapter(channel.type, db, strict=False)
            adapter_type = adapter.__class__.__name__
            try:
                existing_publication = _get_existing_channel_publication(
                    db,
                    company_id=company_id,
                    post_id=post_id,
                    channel_id=channel.id,
                )
                if existing_publication is not None:
                    duration_ms = int((perf_counter() - started_at) * 1000)
                    return ChannelPublishResult(
                        channel_id=channel.id,
                        channel_type=channel.type,
                        adapter_type=adapter_type,
                        success=True,
                        retryable=False,
                        publish_duration_ms=duration_ms,
                        metadata={
                            "external_post_id": existing_publication.external_post_id,
                            "idempotent": True,
                            "channel_publication_id": str(existing_publication.id),
                        },
                        error=None,
                    )

                adapter_result = await adapter.publish_post(post=post, channel=channel)
                external_post_id = str((adapter_result or {}).get("external_post_id") or "").strip()
                if external_post_id:
                    publication = _get_existing_channel_publication(
                        db,
                        company_id=company_id,
                        post_id=post_id,
                        channel_id=channel.id,
                    )
                    if publication is None:
                        publication = ChannelPublication(
                            company_id=company_id,
                            project_id=post.project_id,
                            post_id=post.id,
                            channel_id=channel.id,
                            external_post_id=external_post_id,
                            metadata_json=adapter_result or {},
                        )
                    else:
                        publication.external_post_id = external_post_id
                        publication.metadata_json = adapter_result or publication.metadata_json or {}
                    db.add(publication)
                db.commit()
                duration_ms = int((perf_counter() - started_at) * 1000)
                return ChannelPublishResult(
                    channel_id=channel.id,
                    channel_type=channel.type,
                    adapter_type=adapter_type,
                    success=True,
                    retryable=False,
                    publish_duration_ms=duration_ms,
                    metadata=adapter_result or {},
                    error=None,
                )
            except AdapterAuthError as exc:
                db.rollback()
                channel.status = "disabled"
                db.add(channel)
                db.commit()
                duration_ms = int((perf_counter() - started_at) * 1000)
                return ChannelPublishResult(
                    channel_id=channel.id,
                    channel_type=channel.type,
                    adapter_type=adapter_type,
                    success=False,
                    retryable=False,
                    publish_duration_ms=duration_ms,
                    metadata={
                        "error_code": getattr(exc, "error_code", "adapter_auth_error"),
                        "channel_auth_failed": True,
                        "channel_disabled": True,
                    },
                    error=str(exc),
                )
            except AdapterRetryableError as exc:
                db.rollback()
                duration_ms = int((perf_counter() - started_at) * 1000)
                return ChannelPublishResult(
                    channel_id=channel.id,
                    channel_type=channel.type,
                    adapter_type=adapter_type,
                    success=False,
                    retryable=attempt < policy.max_attempts,
                    publish_duration_ms=duration_ms,
                    metadata={"error_code": getattr(exc, "error_code", "adapter_retryable_error")},
                    error=str(exc),
                )
            except AdapterPermanentError as exc:
                db.rollback()
                duration_ms = int((perf_counter() - started_at) * 1000)
                return ChannelPublishResult(
                    channel_id=channel.id,
                    channel_type=channel.type,
                    adapter_type=adapter_type,
                    success=False,
                    retryable=False,
                    publish_duration_ms=duration_ms,
                    metadata={"error_code": getattr(exc, "error_code", "adapter_permanent_error")},
                    error=str(exc),
                )
            except Exception as exc:
                db.rollback()
                duration_ms = int((perf_counter() - started_at) * 1000)
                return ChannelPublishResult(
                    channel_id=channel.id,
                    channel_type=channel.type,
                    adapter_type=adapter_type,
                    success=False,
                    retryable=attempt < policy.max_attempts,
                    publish_duration_ms=duration_ms,
                    metadata={"error_code": "unhandled_adapter_exception"},
                    error=str(exc),
                )


async def _publish_channels_batch(
    *,
    company_id: UUID,
    post_id: UUID,
    channels: list[Channel],
    attempt: int,
    policies: dict[str, RetryPolicyConfig],
) -> list[ChannelPublishResult]:
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_CHANNEL_PUBLISHES)
    tasks = [
        _publish_channel(
            company_id=company_id,
            post_id=post_id,
            channel_id=channel.id,
            attempt=attempt,
            policy=policies.get(channel.type, _default_retry_policy()),
            semaphore=semaphore,
        )
        for channel in channels
    ]
    return await asyncio.gather(*tasks)


@celery_app.task(name="workers.tasks.ping")
def ping() -> str:
    return "pong"


@celery_app.task(name="workers.tasks.analytics_ping")
def analytics_ping() -> dict:
    return {"status": "ok", "timestamp": datetime.now(UTC).isoformat()}


@celery_app.task(name="workers.tasks.worker_heartbeat")
def worker_heartbeat() -> dict:
    redis_client = get_redis_client()
    now = datetime.now(UTC).isoformat()
    with measure_redis("worker_heartbeat_set"):
        redis_client.set(
            settings.worker_heartbeat_key,
            now,
            ex=max(15, settings.worker_heartbeat_ttl_seconds),
        )
    return {"heartbeat_at": now}


@celery_app.task(name="workers.tasks.reset_monthly_post_usage")
def reset_monthly_post_usage() -> dict:
    with SessionLocal() as db:
        affected = reset_monthly_post_usage_service(db)
        db.commit()
    logger.info("monthly_post_usage_reset completed affected=%s", affected)
    return {"affected_companies": affected}


@celery_app.task(name="workers.tasks.schedule_due_posts")
def schedule_due_posts() -> dict:
    started_at = perf_counter()
    now = datetime.now(UTC)
    enqueued = 0

    with SessionLocal() as db:
        due_posts = db.execute(
            select(Post)
            .where(
                Post.status == PostStatus.SCHEDULED.value,
                Post.publish_at.is_not(None),
                Post.publish_at <= now,
            )
            .order_by(Post.publish_at.asc())
            .limit(500)
        ).scalars().all()
        SCHEDULED_JOBS_CHECKED_TOTAL.inc(len(due_posts))
        increment_background_counter("scheduled_jobs_checked_total", len(due_posts))

        for post in due_posts:
            emit_publish_event(
                db,
                company_id=post.company_id,
                project_id=post.project_id,
                post_id=post.id,
                event_type="PostPublishingStarted",
                status="ok",
                metadata_json={
                    "source": "scheduler",
                    "query_hint": "status=scheduled AND publish_at<=now ORDER BY publish_at ASC LIMIT 500",
                },
            )
            publish_post_async(post.company_id, post.id)
            enqueued += 1

        db.commit()

    logger.info("scheduler_run completed enqueued=%s due_checked_at=%s", enqueued, now.isoformat())
    append_perf_sample("scheduler_scan_duration_ms", (perf_counter() - started_at) * 1000.0)
    return {"enqueued": enqueued}


@celery_app.task(name="workers.tasks.platform_health_intelligence")
def platform_health_intelligence() -> dict:
    with SessionLocal() as db:
        health = calculate_system_health_score(db)
        auto_recovery = execute_auto_recovery(db)
        guardrail_actions = evaluate_platform_guardrails(db, health=health)
        db.commit()
    logger.info(
        "platform_health_intelligence score=%s actions=%s guardrails=%s",
        health.score,
        len(auto_recovery["actions"]),
        len(guardrail_actions["actions"]),
    )
    return {
        "score": health.score,
        "auto_recovery_actions": auto_recovery["actions"],
        "guardrail_actions": guardrail_actions["actions"],
    }


@celery_app.task(name="workers.tasks.refresh_tenant_risk_scores")
def refresh_tenant_risk_scores() -> dict:
    with SessionLocal() as db:
        tenant_ids = [company_id for (company_id,) in db.execute(select(Post.company_id).distinct()).all()]
        refreshed = 0
        for tenant_id in tenant_ids:
            calculate_tenant_risk_score(db, company_id=tenant_id)
            refreshed += 1
        db.commit()
    return {"refreshed": refreshed}


@celery_app.task(name="workers.tasks.refresh_revenue_intelligence")
def refresh_revenue_intelligence() -> dict:
    with SessionLocal() as db:
        overview = calculate_revenue_overview(db)
        db.commit()
    return {"tenant_count": overview["summary"]["tenant_count"], "total_mrr": overview["summary"]["total_mrr"]}


@celery_app.task(name="workers.tasks.performance_baseline_snapshot")
def performance_baseline_snapshot() -> dict:
    with SessionLocal() as db:
        collect_and_store_performance_baselines(db)
        regressions = db.execute(
            select(func.count(PerformanceBaseline.id)).where(PerformanceBaseline.regression_detected.is_(True))
        ).scalar_one_or_none()
        if int(regressions or 0) > 0:
            create_incident(
                db,
                incident_type="performance_regression_detected",
                severity="warning",
                message="Performance baseline regression detected",
                metadata_json={"regressions": int(regressions or 0)},
            )
        db.commit()
    return {"regressions": int(regressions or 0)}


@celery_app.task(name="workers.tasks.schedule_due_automation_rules")
def schedule_due_automation_rules() -> dict:
    now = datetime.now(UTC)
    with SessionLocal() as db:
        result = dispatch_due_time_rules(db, now=now)
        db.commit()

    logger.info(
        "automation_scheduler_completed checked=%s runs_created=%s checked_at=%s",
        result.rules_checked,
        result.runs_created,
        now.isoformat(),
    )
    return {
        "rules_checked": result.rules_checked,
        "runs_created": result.runs_created,
    }


@celery_app.task(name="workers.tasks.process_publish_event_rules")
def process_publish_event_rules() -> dict:
    now = datetime.now(UTC)
    with SessionLocal() as db:
        result = dispatch_event_triggered_rules(db, redis_client=get_redis_client())
        db.commit()

    logger.info(
        "automation_event_scheduler_completed checked=%s runs_created=%s checked_at=%s",
        result.rules_checked,
        result.runs_created,
        now.isoformat(),
    )
    return {
        "rules_checked": result.rules_checked,
        "runs_created": result.runs_created,
    }


@celery_app.task(
    bind=True,
    name="workers.tasks.execute_automation_run",
    max_retries=AUTOMATION_MAX_RETRIES,
    acks_late=True,
)
def execute_automation_run(self, run_id: str) -> dict:
    run_uuid = UUID(run_id)
    attempt = self.request.retries + 1
    with SessionLocal() as db:
        run = db.execute(select(AutomationRun).where(AutomationRun.id == run_uuid)).scalar_one_or_none()
        if run is None:
            logger.warning("automation_run_missing run_id=%s", run_id)
            return {"status": "missing"}
        if run.status in [AutomationRunStatus.SUCCESS.value, AutomationRunStatus.FAILED.value]:
            return {"status": run.status, "reason": "already_terminal"}

        try:
            payload = execute_automation_run_runtime(db, run_id=run_uuid)
            db.commit()
            logger.info(
                "automation_run_completed run_id=%s status=%s attempt=%s",
                run_id,
                payload.get("status"),
                attempt,
            )
            return payload
        except ValueError as exc:
            db.rollback()
            run = db.execute(select(AutomationRun).where(AutomationRun.id == run_uuid)).scalar_one_or_none()
            if run is not None:
                run.status = AutomationRunStatus.FAILED.value
                run.finished_at = datetime.now(UTC)
                run.error_message = str(exc)
                emit_automation_event(
                    db,
                    company_id=run.company_id,
                    project_id=run.project_id,
                    run_id=run.id,
                    event_type="AutomationRunFailed",
                    status="error",
                    metadata_json={"error": str(exc), "attempt": attempt},
                )
                db.commit()
            logger.exception("automation_run_failed_non_retryable run_id=%s", run_id)
            return {"status": "failed", "error": str(exc)}
        except Exception as exc:
            db.rollback()
            run = db.execute(select(AutomationRun).where(AutomationRun.id == run_uuid)).scalar_one_or_none()
            if run is not None:
                emit_automation_event(
                    db,
                    company_id=run.company_id,
                    project_id=run.project_id,
                    run_id=run.id,
                    event_type="AutomationRunRetryScheduled",
                    status="error",
                    metadata_json={"error": str(exc), "attempt": attempt},
                )
                db.commit()
            countdown = min(300, 10 * (2 ** (attempt - 1)))
            logger.warning(
                "automation_run_retry run_id=%s attempt=%s countdown=%s error=%s",
                run_id,
                attempt,
                countdown,
                str(exc),
            )
            try:
                raise self.retry(exc=exc, countdown=countdown)
            except MaxRetriesExceededError:
                run = db.execute(select(AutomationRun).where(AutomationRun.id == run_uuid)).scalar_one_or_none()
                if run is not None:
                    run.status = AutomationRunStatus.FAILED.value
                    run.finished_at = datetime.now(UTC)
                    run.error_message = str(exc)
                    emit_automation_event(
                        db,
                        company_id=run.company_id,
                        project_id=run.project_id,
                        run_id=run.id,
                        event_type="AutomationRunFailed",
                        status="error",
                        metadata_json={"error": str(exc), "attempt": attempt, "reason": "max_retries_exceeded"},
                    )
                    db.commit()
                logger.exception("automation_run_max_retries run_id=%s", run_id)
                return {"status": "failed", "error": str(exc)}


@celery_app.task(bind=True, name="workers.tasks.publish_post", max_retries=MAX_TASK_RETRIES, acks_late=True)
def publish_post(self, company_id: str, post_id: str) -> dict:
    PUBLISH_ATTEMPTS_TOTAL.inc()
    increment_background_counter("publish_attempts_total")
    company_uuid = UUID(company_id)
    post_uuid = UUID(post_id)
    attempt = self.request.retries + 1
    redis_client = get_redis_client()
    lock_token = _acquire_publish_lock(redis_client, post_id=post_uuid)
    if lock_token is None:
        logger.info("publish_post_skipped_locked company_id=%s post_id=%s", company_id, post_id)
        return {"status": "skipped", "reason": "lock_not_acquired"}

    try:
        with SessionLocal() as db:
            post = db.execute(
                select(Post).where(Post.id == post_uuid, Post.company_id == company_uuid)
            ).scalar_one_or_none()
            if post is None:
                logger.warning("publish_post_not_found company_id=%s post_id=%s", company_id, post_id)
                return {"status": "missing"}

            if post.status == PostStatus.PUBLISHED.value:
                logger.info("publish_post_skip_already_published company_id=%s post_id=%s", company_id, post_id)
                return {"status": "skipped", "reason": "already_published"}

            if post.status == PostStatus.PUBLISHING.value:
                logger.info("publish_post_skip_in_progress company_id=%s post_id=%s", company_id, post_id)
                return {"status": "skipped", "reason": "already_publishing"}

            if post.status not in {PostStatus.SCHEDULED.value, PostStatus.DRAFT.value}:
                logger.info(
                    "publish_post_skip_invalid_state company_id=%s post_id=%s status=%s",
                    company_id,
                    post_id,
                    post.status,
                )
                return {"status": "skipped", "post_status": post.status}

            post.status = PostStatus.PUBLISHING.value
            post.last_error = None
            db.commit()

            channels = get_active_channels(db, company_id=company_uuid, project_id=post.project_id)
            if not channels:
                PUBLISH_FAILURES_TOTAL.inc()
                increment_background_counter("publish_failures_total")
                post.status = PostStatus.FAILED.value
                post.last_error = "No active channels found for project"
                emit_publish_event(
                    db,
                    company_id=post.company_id,
                    project_id=post.project_id,
                    post_id=post.id,
                    event_type="PostPublishFailed",
                    status="error",
                    attempt=attempt,
                    metadata_json={"error": post.last_error},
                )
                _record_failed_job(
                    db,
                    job_type="publish_post",
                    payload={"company_id": company_id, "post_id": post_id, "reason": "no_active_channels"},
                    error_message=post.last_error,
                )
                db.commit()
                return {"status": "failed", "error": post.last_error}

            successful_channel_ids = set(
                db.execute(
                    select(PublishEvent.channel_id).where(
                        PublishEvent.company_id == company_uuid,
                        PublishEvent.post_id == post_uuid,
                        PublishEvent.channel_id.is_not(None),
                        PublishEvent.event_type == "ChannelPublishSucceeded",
                        PublishEvent.status == "ok",
                    )
                ).scalars().all()
            )

            pending_channels = [channel for channel in channels if channel.id not in successful_channel_ids]
            policies = _load_retry_policies(db, {channel.type for channel in pending_channels})

            publish_results: list[ChannelPublishResult] = []
            if pending_channels:
                publish_results = asyncio.run(
                    _publish_channels_batch(
                        company_id=company_uuid,
                        post_id=post_uuid,
                        channels=pending_channels,
                        attempt=attempt,
                        policies=policies,
                    )
                )

            success_count = len(successful_channel_ids) + sum(1 for result in publish_results if result.success)
            failed_results = [result for result in publish_results if not result.success]

            for result in publish_results:
                metadata = {
                    "channel_type": result.channel_type,
                    "platform": result.channel_type,
                    "adapter_type": result.adapter_type,
                    "publish_duration_ms": result.publish_duration_ms,
                    "publish_latency_ms": result.publish_duration_ms,
                    "retry_count": max(0, attempt - 1),
                    "success": result.success,
                    "retryable": result.retryable,
                    **(result.metadata or {}),
                }
                if result.error:
                    metadata["error"] = result.error
                emit_publish_event(
                    db,
                    company_id=post.company_id,
                    project_id=post.project_id,
                    post_id=post.id,
                    channel_id=result.channel_id,
                    event_type="ChannelPublishSucceeded" if result.success else "ChannelPublishFailed",
                    status="ok" if result.success else "error",
                    attempt=attempt,
                    metadata_json=metadata,
                )
                if result.metadata.get("channel_auth_failed"):
                    emit_publish_event(
                        db,
                        company_id=post.company_id,
                        project_id=post.project_id,
                        post_id=post.id,
                        channel_id=result.channel_id,
                        event_type="ChannelAuthFailed",
                        status="error",
                        attempt=attempt,
                        metadata_json=metadata,
                    )

            channels_total = len(channels)
            summary_metadata = {
                "channels_total": channels_total,
                "channels_success": success_count,
                "channels_failed": len(failed_results),
                "attempt": attempt,
            }

            if failed_results:
                PUBLISH_FAILURES_TOTAL.inc()
                increment_background_counter("publish_failures_total")
                error_summary = "; ".join(
                    f"{result.channel_type}:{result.error or 'unknown'}" for result in failed_results
                )
                post.last_error = error_summary
                if success_count > 0:
                    post.status = PostStatus.PUBLISHED_PARTIAL.value
                    emit_publish_event(
                        db,
                        company_id=post.company_id,
                        project_id=post.project_id,
                        post_id=post.id,
                        event_type="PostPublishedPartial",
                        status="error",
                        attempt=attempt,
                        metadata_json={**summary_metadata, "error": error_summary},
                    )
                else:
                    post.status = PostStatus.FAILED.value
                    emit_publish_event(
                        db,
                        company_id=post.company_id,
                        project_id=post.project_id,
                        post_id=post.id,
                        event_type="PostPublishFailed",
                        status="error",
                        attempt=attempt,
                        metadata_json={**summary_metadata, "error": error_summary},
                    )
            else:
                post.status = PostStatus.PUBLISHED.value
                post.last_error = None
                emit_publish_event(
                    db,
                    company_id=post.company_id,
                    project_id=post.project_id,
                    post_id=post.id,
                    event_type="PostPublished",
                    status="ok",
                    attempt=attempt,
                    metadata_json=summary_metadata,
                )

            db.commit()

            retryable_failures = [result for result in failed_results if result.retryable]
            if retryable_failures:
                delays = []
                for result in retryable_failures:
                    policy = policies.get(result.channel_type, _default_retry_policy())
                    delays.append(_compute_retry_delay_seconds(policy, attempt))
                retry_countdown = max(1, min(delays)) if delays else DEFAULT_RETRY_DELAY_SECONDS
                retry_countdown = max(retry_countdown, min(1800, 30 * (2 ** (attempt - 1))))

                # Requeue through scheduler-safe state transition.
                post.status = PostStatus.SCHEDULED.value
                db.commit()

                logger.warning(
                    "publish_post_retry_scheduled company_id=%s post_id=%s attempt=%s countdown=%s failed_channels=%s",
                    company_id,
                    post_id,
                    attempt,
                    retry_countdown,
                    ",".join(sorted({result.channel_type for result in retryable_failures})),
                )
                try:
                    raise self.retry(
                        exc=RuntimeError("One or more channels failed and are retryable"),
                        countdown=retry_countdown,
                    )
                except MaxRetriesExceededError:
                    logger.exception(
                        "publish_post_max_retries company_id=%s post_id=%s", company_id, post_id
                    )
                    post.status = PostStatus.FAILED.value
                    _record_failed_job(
                        db,
                        job_type="publish_post",
                        payload={"company_id": company_id, "post_id": post_id, "attempt": attempt},
                        error_message=post.last_error or "Max retries exceeded",
                    )
                    db.commit()
                    return {"status": post.status, "error": post.last_error}

            if post.status == PostStatus.FAILED.value:
                log_audit_event(
                    db,
                    company_id=post.company_id,
                    action="publish.failed",
                    metadata={
                        "post_id": str(post.id),
                        "project_id": str(post.project_id),
                        "attempt": attempt,
                        "last_error": post.last_error,
                    },
                )
                _record_failed_job(
                    db,
                    job_type="publish_post",
                    payload={"company_id": company_id, "post_id": post_id, "attempt": attempt},
                    error_message=post.last_error or "Publish failed",
                )
                db.commit()

            logger.info(
                "publish_post_completed company_id=%s post_id=%s project_id=%s status=%s channels_success=%s channels_failed=%s",
                company_id,
                post_id,
                post.project_id,
                post.status,
                success_count,
                len(failed_results),
            )
            if post.status in {PostStatus.PUBLISHED.value, PostStatus.PUBLISHED_PARTIAL.value}:
                log_audit_event(
                    db,
                    company_id=post.company_id,
                    action="publish.completed",
                    metadata={
                        "post_id": str(post.id),
                        "project_id": str(post.project_id),
                        "status": post.status,
                        "channels_success": success_count,
                        "channels_failed": len(failed_results),
                    },
                )
                db.commit()
            return {
                "status": post.status,
                "channels_total": channels_total,
                "channels_success": success_count,
                "channels_failed": len(failed_results),
            }
    finally:
        _release_publish_lock(redis_client, post_id=post_uuid, token=lock_token)
