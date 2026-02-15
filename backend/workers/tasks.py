import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from time import perf_counter
from uuid import UUID

from celery.exceptions import MaxRetriesExceededError
from sqlalchemy import select

from app.application.services.publishing_service import emit_publish_event, get_active_channels, publish_post_async
from app.domain.models.channel import Channel
from app.domain.models.channel_publication import ChannelPublication
from app.domain.models.channel_retry_policy import ChannelRetryPolicy, RetryBackoffStrategy
from app.domain.models.post import Post, PostStatus
from app.domain.models.publish_event import PublishEvent
from app.integrations.channel_adapters import (
    AdapterAuthError,
    AdapterPermanentError,
    AdapterRetryableError,
    get_channel_adapter,
)
from app.integrations.platform_rate_limit_service import check_platform_rate_limit
from app.infrastructure.cache.redis_client import get_redis_client
from app.infrastructure.db.session import SessionLocal
from workers.celery_app import celery_app

logger = logging.getLogger(__name__)

DEFAULT_MAX_ATTEMPTS = 5
DEFAULT_BACKOFF_STRATEGY = RetryBackoffStrategy.EXPONENTIAL.value
DEFAULT_RETRY_DELAY_SECONDS = 30
MAX_TASK_RETRIES = 100
MAX_CONCURRENT_CHANNEL_PUBLISHES = 5


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


@celery_app.task(name="workers.tasks.schedule_due_posts")
def schedule_due_posts() -> dict:
    now = datetime.now(UTC)
    enqueued = 0

    with SessionLocal() as db:
        due_posts = db.execute(
            select(Post).where(
                Post.status == PostStatus.SCHEDULED.value,
                Post.publish_at.is_not(None),
                Post.publish_at <= now,
            )
        ).scalars().all()

        for post in due_posts:
            post.status = PostStatus.PUBLISHING.value
            post.last_error = None
            emit_publish_event(
                db,
                company_id=post.company_id,
                project_id=post.project_id,
                post_id=post.id,
                event_type="PostPublishingStarted",
                status="ok",
                metadata_json={"source": "scheduler"},
            )
            publish_post_async(post.company_id, post.id)
            enqueued += 1

        db.commit()

    logger.info("scheduler_run completed enqueued=%s due_checked_at=%s", enqueued, now.isoformat())
    return {"enqueued": enqueued}


@celery_app.task(bind=True, name="workers.tasks.publish_post", max_retries=MAX_TASK_RETRIES, acks_late=True)
def publish_post(self, company_id: str, post_id: str) -> dict:
    company_uuid = UUID(company_id)
    post_uuid = UUID(post_id)
    attempt = self.request.retries + 1

    with SessionLocal() as db:
        post = db.execute(
            select(Post).where(Post.id == post_uuid, Post.company_id == company_uuid)
        ).scalar_one_or_none()
        if post is None:
            logger.warning("publish_post_not_found company_id=%s post_id=%s", company_id, post_id)
            return {"status": "missing"}

        allowed_states = {
            PostStatus.PUBLISHING.value,
            PostStatus.SCHEDULED.value,
            PostStatus.PUBLISHED_PARTIAL.value,
            PostStatus.FAILED.value,
        }
        if post.status not in allowed_states:
            logger.info(
                "publish_post_skip_invalid_state company_id=%s post_id=%s status=%s",
                company_id,
                post_id,
                post.status,
            )
            return {"status": "skipped", "post_status": post.status}

        channels = get_active_channels(db, company_id=company_uuid, project_id=post.project_id)
        if not channels:
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
                return {"status": post.status, "error": post.last_error}

        logger.info(
            "publish_post_completed company_id=%s post_id=%s project_id=%s status=%s channels_success=%s channels_failed=%s",
            company_id,
            post_id,
            post.project_id,
            post.status,
            success_count,
            len(failed_results),
        )
        return {
            "status": post.status,
            "channels_total": channels_total,
            "channels_success": success_count,
            "channels_failed": len(failed_results),
        }
