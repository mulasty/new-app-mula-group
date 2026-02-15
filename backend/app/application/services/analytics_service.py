import json
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID

from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import and_, case, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.post import Post, PostStatus
from app.domain.models.publish_event import PublishEvent
from app.domain.models.website_publication import WebsitePublication

ANALYTICS_CACHE_TTL_SECONDS = 45
ALLOWED_TIME_RANGES = {"7d": 7, "30d": 30, "90d": 90}


def parse_time_range_days(value: str) -> int:
    if value not in ALLOWED_TIME_RANGES:
        raise ValueError("Invalid range. Use one of: 7d, 30d, 90d")
    return ALLOWED_TIME_RANGES[value]


def _cache_key(prefix: str, *, company_id: UUID, project_id: UUID | None = None, suffix: str | None = None) -> str:
    parts = ["analytics", prefix, str(company_id), str(project_id) if project_id else "all"]
    if suffix:
        parts.append(suffix)
    return ":".join(parts)


def _cache_get(redis_client: Redis, key: str):
    try:
        cached = redis_client.get(key)
        if cached:
            return json.loads(cached)
    except (RedisError, json.JSONDecodeError):
        return None
    return None


def _cache_set(redis_client: Redis, key: str, payload: dict | list) -> None:
    try:
        redis_client.setex(key, ANALYTICS_CACHE_TTL_SECONDS, json.dumps(payload))
    except RedisError:
        return


async def get_publishing_summary(
    db: AsyncSession,
    redis_client: Redis,
    *,
    company_id: UUID,
    project_id: UUID | None = None,
) -> dict:
    cache_key = _cache_key("publishing-summary", company_id=company_id, project_id=project_id)
    cached = _cache_get(redis_client, cache_key)
    if cached is not None:
        return cached

    filters = [Post.company_id == company_id]
    if project_id:
        filters.append(Post.project_id == project_id)

    counts_stmt = select(Post.status, func.count(Post.id)).where(*filters).group_by(Post.status)
    counts_rows = (await db.execute(counts_stmt)).all()

    counts = {
        PostStatus.SCHEDULED.value: 0,
        PostStatus.PUBLISHING.value: 0,
        PostStatus.PUBLISHED.value: 0,
        PostStatus.PUBLISHED_PARTIAL.value: 0,
        PostStatus.FAILED.value: 0,
    }
    for status, total in counts_rows:
        if status in counts:
            counts[status] = int(total or 0)

    successful_publications = counts[PostStatus.PUBLISHED.value] + counts[PostStatus.PUBLISHED_PARTIAL.value]
    attempts = successful_publications + counts[PostStatus.FAILED.value]
    success_rate = round((successful_publications / attempts), 4) if attempts > 0 else 0.0

    schedule_filters = [
        PublishEvent.company_id == company_id,
        PublishEvent.event_type == "PostScheduled",
        PublishEvent.status == "ok",
    ]
    if project_id:
        schedule_filters.append(PublishEvent.project_id == project_id)

    first_schedule_subq = (
        select(
            PublishEvent.post_id.label("post_id"),
            func.min(PublishEvent.created_at).label("scheduled_at"),
        )
        .where(*schedule_filters)
        .group_by(PublishEvent.post_id)
        .subquery()
    )

    publication_filters = [WebsitePublication.company_id == company_id]
    if project_id:
        publication_filters.append(WebsitePublication.project_id == project_id)

    avg_stmt = (
        select(
            func.avg(
                func.extract(
                    "epoch",
                    WebsitePublication.published_at - first_schedule_subq.c.scheduled_at,
                )
            )
        )
        .select_from(WebsitePublication)
        .join(first_schedule_subq, first_schedule_subq.c.post_id == WebsitePublication.post_id)
        .where(*publication_filters)
    )
    avg_seconds = (await db.execute(avg_stmt)).scalar_one_or_none()

    payload = {
        "scheduled": counts[PostStatus.SCHEDULED.value],
        "publishing": counts[PostStatus.PUBLISHING.value],
        "published": successful_publications,
        "failed": counts[PostStatus.FAILED.value],
        "success_rate": float(success_rate),
        "avg_publish_time_sec": round(float(avg_seconds or 0.0), 2),
    }

    _cache_set(redis_client, cache_key, payload)
    return payload


async def get_publishing_timeseries(
    db: AsyncSession,
    redis_client: Redis,
    *,
    company_id: UUID,
    range_days: int,
    project_id: UUID | None = None,
) -> list[dict]:
    suffix = f"{range_days}d"
    cache_key = _cache_key("publishing-timeseries", company_id=company_id, project_id=project_id, suffix=suffix)
    cached = _cache_get(redis_client, cache_key)
    if cached is not None:
        return cached

    start_day = datetime.now(UTC).date() - timedelta(days=range_days - 1)
    start_dt = datetime.combine(start_day, time.min, tzinfo=UTC)

    filters = [
        PublishEvent.company_id == company_id,
        PublishEvent.created_at >= start_dt,
        PublishEvent.event_type.in_(["PostPublished", "PostPublishedPartial", "PostPublishFailed"]),
    ]
    if project_id:
        filters.append(PublishEvent.project_id == project_id)

    day_expr = func.date(PublishEvent.created_at)
    stmt = (
        select(
            day_expr.label("date"),
            func.sum(
                case(
                    (
                        and_(
                            PublishEvent.event_type.in_(["PostPublished", "PostPublishedPartial"]),
                            PublishEvent.status.in_(["ok", "error"]),
                        ),
                        1,
                    ),
                    else_=0,
                )
            ).label("published"),
            func.sum(
                case(
                    (and_(PublishEvent.event_type == "PostPublishFailed", PublishEvent.status == "error"), 1),
                    else_=0,
                )
            ).label("failed"),
        )
        .where(*filters)
        .group_by(day_expr)
        .order_by(day_expr)
    )
    rows = (await db.execute(stmt)).all()
    rows_by_day = {row.date: row for row in rows}

    payload: list[dict] = []
    for day_offset in range(range_days):
        current_day = start_day + timedelta(days=day_offset)
        row = rows_by_day.get(current_day)
        payload.append(
            {
                "date": current_day.isoformat(),
                "published": int(row.published or 0) if row else 0,
                "failed": int(row.failed or 0) if row else 0,
            }
        )

    _cache_set(redis_client, cache_key, payload)
    return payload


async def get_activity_stream(
    db: AsyncSession,
    redis_client: Redis,
    *,
    company_id: UUID,
    limit: int = 50,
    project_id: UUID | None = None,
) -> list[dict]:
    normalized_limit = max(1, min(limit, 200))
    cache_key = _cache_key(
        "activity-stream",
        company_id=company_id,
        project_id=project_id,
        suffix=str(normalized_limit),
    )
    cached = _cache_get(redis_client, cache_key)
    if cached is not None:
        return cached

    filters = [PublishEvent.company_id == company_id]
    if project_id:
        filters.append(PublishEvent.project_id == project_id)

    stmt = (
        select(
            PublishEvent.created_at,
            PublishEvent.post_id,
            PublishEvent.event_type,
            PublishEvent.status,
            PublishEvent.metadata_json,
        )
        .where(*filters)
        .order_by(desc(PublishEvent.created_at))
        .limit(normalized_limit)
    )
    rows = (await db.execute(stmt)).all()
    payload = [
        {
            "timestamp": row.created_at.isoformat(),
            "post_id": str(row.post_id),
            "event_type": row.event_type,
            "status": row.status,
            "metadata": row.metadata_json or {},
        }
        for row in rows
    ]

    _cache_set(redis_client, cache_key, payload)
    return payload
