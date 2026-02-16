from __future__ import annotations

from contextlib import contextmanager
from time import perf_counter

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.responses import Response

REQUESTS_TOTAL = Counter(
    "total_requests",
    "Total HTTP requests",
    labelnames=("method", "path", "status"),
)
REQUEST_LATENCY_SECONDS = Histogram(
    "request_latency_seconds",
    "HTTP request latency in seconds",
    labelnames=("method", "path"),
)
DB_QUERY_DURATION_SECONDS = Histogram(
    "db_query_duration_seconds",
    "Database query duration in seconds",
    labelnames=("operation",),
)
REDIS_LATENCY_SECONDS = Histogram(
    "redis_latency_seconds",
    "Redis command latency in seconds",
    labelnames=("operation",),
)
PUBLISH_ATTEMPTS_TOTAL = Counter(
    "publish_attempts_total",
    "Number of publish attempts executed by workers",
)
PUBLISH_FAILURES_TOTAL = Counter(
    "publish_failures_total",
    "Number of failed publish attempts in workers",
)
SCHEDULED_JOBS_CHECKED_TOTAL = Counter(
    "scheduled_jobs_checked_total",
    "Number of scheduled jobs scanned by scheduler",
)

BACKGROUND_COUNTER_KEYS = {
    "publish_attempts_total": "metrics:publish_attempts_total",
    "publish_failures_total": "metrics:publish_failures_total",
    "scheduled_jobs_checked_total": "metrics:scheduled_jobs_checked_total",
}
_last_background_counter_values: dict[str, float] = {
    metric_name: 0.0 for metric_name in BACKGROUND_COUNTER_KEYS
}


def record_request(method: str, path: str, status_code: int, duration_seconds: float) -> None:
    REQUESTS_TOTAL.labels(method=method, path=path, status=str(status_code)).inc()
    REQUEST_LATENCY_SECONDS.labels(method=method, path=path).observe(duration_seconds)


def observe_db_query(duration_seconds: float, operation: str = "sql") -> None:
    DB_QUERY_DURATION_SECONDS.labels(operation=operation).observe(duration_seconds)


def observe_redis_latency(duration_seconds: float, operation: str) -> None:
    REDIS_LATENCY_SECONDS.labels(operation=operation).observe(duration_seconds)


def increment_background_counter(metric_name: str, amount: int = 1) -> None:
    redis_key = BACKGROUND_COUNTER_KEYS.get(metric_name)
    if redis_key is None:
        return
    try:
        from app.infrastructure.cache.redis_client import get_redis_client

        redis_client = get_redis_client()
        with measure_redis("metrics_background_counter_incr"):
            redis_client.incrby(redis_key, amount)
    except Exception:
        # Keep publish/scheduler flow resilient even when Redis metrics write fails.
        return


def _sync_background_counters_from_redis() -> None:
    try:
        from app.infrastructure.cache.redis_client import get_redis_client

        redis_client = get_redis_client()
        with measure_redis("metrics_background_counter_sync"):
            raw_values = redis_client.mget(list(BACKGROUND_COUNTER_KEYS.values()))
    except Exception:
        return

    current_by_metric: dict[str, float] = {}
    for idx, metric_name in enumerate(BACKGROUND_COUNTER_KEYS):
        raw_value = raw_values[idx] if raw_values else None
        current_by_metric[metric_name] = float(raw_value or 0.0)

    mapping = {
        "publish_attempts_total": PUBLISH_ATTEMPTS_TOTAL,
        "publish_failures_total": PUBLISH_FAILURES_TOTAL,
        "scheduled_jobs_checked_total": SCHEDULED_JOBS_CHECKED_TOTAL,
    }
    for metric_name, collector in mapping.items():
        last_value = _last_background_counter_values.get(metric_name, 0.0)
        current_value = current_by_metric.get(metric_name, 0.0)
        delta = current_value - last_value
        if delta > 0:
            collector.inc(delta)
        _last_background_counter_values[metric_name] = current_value


@contextmanager
def measure_redis(operation: str):
    started_at = perf_counter()
    try:
        yield
    finally:
        observe_redis_latency(perf_counter() - started_at, operation=operation)


def metrics_response() -> Response:
    _sync_background_counters_from_redis()
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
