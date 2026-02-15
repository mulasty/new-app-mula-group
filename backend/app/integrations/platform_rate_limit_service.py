from dataclasses import dataclass
from datetime import UTC, datetime

from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models.platform_rate_limit import PlatformRateLimit

DEFAULT_REQUESTS_PER_MINUTE = 120


@dataclass(frozen=True)
class PlatformRateLimitResult:
    platform: str
    limit: int
    current: int
    allowed: bool
    retry_after_seconds: int


def _load_limit(db: Session, platform: str) -> int:
    row = db.execute(
        select(PlatformRateLimit).where(PlatformRateLimit.platform == platform)
    ).scalar_one_or_none()
    if row is None:
        return DEFAULT_REQUESTS_PER_MINUTE
    return max(1, int(row.requests_per_minute))


def check_platform_rate_limit(
    *,
    db: Session,
    redis_client: Redis,
    platform: str,
) -> PlatformRateLimitResult:
    normalized_platform = platform.strip().lower()
    limit = _load_limit(db, normalized_platform)
    now = datetime.now(UTC)
    window_key = f"platform_rate_limit:{normalized_platform}:{now:%Y%m%d%H%M}"

    try:
        current = int(redis_client.incr(window_key))
        if current == 1:
            redis_client.expire(window_key, 65)
        ttl = int(redis_client.ttl(window_key))
        retry_after = ttl if ttl > 0 else 60
    except RedisError:
        # Fail-open to avoid hard outage on transient Redis issues.
        return PlatformRateLimitResult(
            platform=normalized_platform,
            limit=limit,
            current=0,
            allowed=True,
            retry_after_seconds=0,
        )

    return PlatformRateLimitResult(
        platform=normalized_platform,
        limit=limit,
        current=current,
        allowed=current <= limit,
        retry_after_seconds=retry_after,
    )
