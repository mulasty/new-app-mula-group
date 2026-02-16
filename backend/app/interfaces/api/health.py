from time import perf_counter

from fastapi import APIRouter, Response, status
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.infrastructure.cache.redis_client import get_redis_client
from app.infrastructure.db.session import SessionLocal
from app.infrastructure.observability.metrics import measure_redis, metrics_response

router = APIRouter()


@router.get("/health", status_code=status.HTTP_200_OK)
def health_check() -> dict:
    db_status = "up"
    redis_status = "up"
    db_latency_ms: float | None = None
    redis_latency_ms: float | None = None
    worker_alive = False

    try:
        db_started_at = perf_counter()
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        db_latency_ms = round((perf_counter() - db_started_at) * 1000, 2)
    except SQLAlchemyError:
        db_status = "down"

    try:
        redis_client = get_redis_client()
        redis_started_at = perf_counter()
        with measure_redis("health_ping"):
            redis_client.ping()
        redis_latency_ms = round((perf_counter() - redis_started_at) * 1000, 2)

        with measure_redis("health_worker_heartbeat_check"):
            worker_alive = bool(redis_client.exists(settings.worker_heartbeat_key))
    except RedisError:
        redis_status = "down"
        worker_alive = False

    overall = "ok" if db_status == "up" and redis_status == "up" and worker_alive else "degraded"

    return {
        "status": overall,
        "services": {
            "api": "up",
            "database": db_status,
            "redis": redis_status,
            "worker_alive": worker_alive,
            "db_latency_ms": db_latency_ms,
            "redis_latency_ms": redis_latency_ms,
        },
    }


@router.get("/ready", status_code=status.HTTP_200_OK)
def readiness_check(response: Response) -> dict:
    payload = health_check()
    if (
        payload["services"]["database"] != "up"
        or payload["services"]["redis"] != "up"
        or payload["services"]["worker_alive"] is not True
    ):
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "not_ready", "services": payload["services"]}
    return {"status": "ready", "services": payload["services"]}


@router.get("/metrics", include_in_schema=False)
def metrics():
    return metrics_response()
