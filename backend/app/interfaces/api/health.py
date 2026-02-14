from fastapi import APIRouter, status
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.infrastructure.cache.redis_client import get_redis_client
from app.infrastructure.db.session import SessionLocal

router = APIRouter()


@router.get("/health", status_code=status.HTTP_200_OK)
def health_check() -> dict:
    db_status = "up"
    redis_status = "up"

    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        db_status = "down"

    try:
        redis_client = get_redis_client()
        redis_client.ping()
    except RedisError:
        redis_status = "down"

    overall = "ok" if db_status == "up" and redis_status == "up" else "degraded"

    return {
        "status": overall,
        "services": {
            "api": "up",
            "database": db_status,
            "redis": redis_status,
        },
    }
