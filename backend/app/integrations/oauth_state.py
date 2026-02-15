import base64
import hashlib
import hmac
import json
import secrets
import time
from uuid import UUID

from fastapi import HTTPException, status
from redis.exceptions import RedisError

from app.core.config import settings
from app.infrastructure.cache.redis_client import get_redis_client

STATE_TTL_SECONDS = 600


def _urlsafe_b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _urlsafe_b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("utf-8"))


def _sign_state(encoded_payload: str) -> str:
    secret = settings.jwt_secret_key.encode("utf-8")
    signature = hmac.new(secret, encoded_payload.encode("utf-8"), hashlib.sha256).digest()
    return _urlsafe_b64encode(signature)


def _build_nonce_key(provider: str, nonce: str) -> str:
    return f"oauth_state:{provider}:{nonce}"


def create_oauth_state(
    *,
    provider: str,
    company_id: UUID,
    user_id: UUID,
    project_id: UUID | None = None,
    extra: dict | None = None,
    ttl_seconds: int = STATE_TTL_SECONDS,
) -> str:
    now = int(time.time())
    nonce = secrets.token_urlsafe(24)
    payload = {
        "provider": provider,
        "company_id": str(company_id),
        "user_id": str(user_id),
        "project_id": str(project_id) if project_id else None,
        "nonce": nonce,
        "iat": now,
        "exp": now + ttl_seconds,
    }
    if extra:
        payload["extra"] = extra

    raw_payload = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    encoded_payload = _urlsafe_b64encode(raw_payload)
    signature = _sign_state(encoded_payload)
    state = f"{encoded_payload}.{signature}"

    redis_client = get_redis_client()
    try:
        nonce_key = _build_nonce_key(provider, nonce)
        redis_client.setex(nonce_key, ttl_seconds, json.dumps(payload, separators=(",", ":")))
    except RedisError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to initialize OAuth state",
        ) from exc

    return state


def verify_and_consume_oauth_state(state: str, *, provider: str) -> dict:
    try:
        encoded_payload, signature = state.split(".", 1)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OAuth state format") from exc

    expected_signature = _sign_state(encoded_payload)
    if not hmac.compare_digest(signature, expected_signature):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OAuth state signature")

    try:
        payload = json.loads(_urlsafe_b64decode(encoded_payload))
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OAuth state payload") from exc

    if payload.get("provider") != provider:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OAuth state provider")

    exp = int(payload.get("exp", 0))
    if exp <= int(time.time()):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OAuth state expired")

    nonce = str(payload.get("nonce") or "")
    if not nonce:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OAuth state nonce missing")

    nonce_key = _build_nonce_key(provider, nonce)
    redis_client = get_redis_client()
    try:
        cached = redis_client.get(nonce_key)
        if not cached:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OAuth state already used or expired")
        redis_client.delete(nonce_key)
    except RedisError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to validate OAuth state",
        ) from exc

    return payload
