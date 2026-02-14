from redis import Redis

from app.core.config import settings


def get_redis_client() -> Redis:
    return Redis.from_url(settings.cache_redis_url, decode_responses=True)
