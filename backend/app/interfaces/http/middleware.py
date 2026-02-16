from datetime import UTC, datetime
import logging
from time import perf_counter
from uuid import UUID, uuid4

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.core.tenant import reset_current_tenant, set_current_tenant
from app.infrastructure.db.session import SessionLocal
from app.infrastructure.cache.redis_client import get_redis_client
from app.infrastructure.logging.context import (
    reset_request_id,
    reset_tenant_id,
    set_request_id,
    set_tenant_id,
)
from app.infrastructure.observability.metrics import measure_redis, record_request
from app.application.services.feature_flag_service import is_feature_enabled
from app.application.services.platform_ops_service import (
    append_perf_sample,
    is_global_publish_paused,
    is_tenant_publish_paused,
)
from app.application.services.billing_service import (
    PLAN_LIMIT_ERROR,
    enforce_connector_limit,
    enforce_post_limit,
    enforce_project_limit,
)

logger = logging.getLogger("app")


class TenantContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        tenant_header = request.headers.get("X-Tenant-ID")
        tenant_token = None
        log_tenant_token = None

        if tenant_header:
            try:
                tenant_id = UUID(tenant_header)
                tenant_token = set_current_tenant(tenant_id)
                log_tenant_token = set_tenant_id(str(tenant_id))
            except ValueError:
                trace_id = getattr(request.state, "request_id", None) or str(uuid4())
                return JSONResponse(
                    status_code=400,
                    content={
                        "error_code": "invalid_tenant_header",
                        "message": "Invalid X-Tenant-ID header",
                        "trace_id": trace_id,
                    },
                )

        try:
            response = await call_next(request)
            return response
        finally:
            if tenant_token is not None:
                reset_current_tenant(tenant_token)
            if log_tenant_token is not None:
                reset_tenant_id(log_tenant_token)


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        started_at = perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            duration_seconds = perf_counter() - started_at
            append_perf_sample("request_latency_ms", duration_seconds * 1000.0)
            record_request(
                method=request.method,
                path=request.url.path,
                status_code=status_code,
                duration_seconds=duration_seconds,
            )


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid4())
        request.state.request_id = request_id
        request_token = set_request_id(request_id)
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            reset_request_id(request_token)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = "default-src 'self'; frame-ancestors 'none'; object-src 'none';"
        return response


class PlanEnforcementMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        tenant_header = request.headers.get("X-Tenant-ID")
        if not tenant_header:
            return await call_next(request)

        method = request.method.upper()
        path = request.url.path
        if method == "POST" and path in {"/projects", "/posts", "/channels"}:
            try:
                tenant_id = UUID(tenant_header)
            except ValueError:
                return await call_next(request)

            try:
                with SessionLocal() as db:
                    if path == "/projects":
                        enforce_project_limit(db, company_id=tenant_id)
                    elif path == "/posts":
                        enforce_post_limit(db, company_id=tenant_id)
                    elif path == "/channels":
                        enforce_connector_limit(db, company_id=tenant_id)
            except Exception as exc:
                status_code = getattr(exc, "status_code", None)
                detail = getattr(exc, "detail", None)
                if status_code == 403 and isinstance(detail, dict) and detail.get("error_code") == "PLAN_LIMIT_EXCEEDED":
                    trace_id = getattr(request.state, "request_id", None) or str(uuid4())
                    return JSONResponse(status_code=403, content={**PLAN_LIMIT_ERROR, "trace_id": trace_id})
                if status_code is None:
                    logger.exception("plan_enforcement_middleware_error")

        return await call_next(request)


class TenantRateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, requests_per_minute: int = 120):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.redis = get_redis_client()

    async def dispatch(self, request: Request, call_next):
        tenant_header = request.headers.get("X-Tenant-ID")
        if tenant_header:
            try:
                now = datetime.now(UTC)
                minute_key = now.strftime("%Y%m%d%H%M")
                prev_minute_key = (now.replace(second=0, microsecond=0)).timestamp() - 60
                prev_minute = datetime.fromtimestamp(prev_minute_key, tz=UTC).strftime("%Y%m%d%H%M")
                current_key = f"rate:{tenant_header}:{minute_key}"
                previous_key = f"rate:{tenant_header}:{prev_minute}"

                pipeline = self.redis.pipeline()
                pipeline.incr(current_key, 1)
                pipeline.expire(current_key, 120)
                pipeline.get(previous_key)
                with measure_redis("rate_limit_pipeline"):
                    current_count, _, previous_count_raw = pipeline.execute()
                previous_count = int(previous_count_raw or 0)
                elapsed_seconds = now.second + (now.microsecond / 1_000_000)
                previous_weight = max(0.0, 1.0 - (elapsed_seconds / 60.0))
                sliding_count = float(current_count) + (previous_count * previous_weight)

                if sliding_count > self.requests_per_minute:
                    violation_key = f"tenant:rate_limit_violations:{tenant_header}"
                    self.redis.incrby(violation_key, 1)
                    self.redis.expire(violation_key, 7 * 24 * 3600)
                    trace_id = getattr(request.state, "request_id", None) or str(uuid4())
                    return JSONResponse(
                        status_code=429,
                        content={
                            "error_code": "rate_limit_exceeded",
                            "message": "Tenant rate limit exceeded",
                            "trace_id": trace_id,
                        },
                    )
                throttle_key = f"tenant:throttle:{tenant_header}"
                if str(self.redis.get(throttle_key) or "0") == "1":
                    trace_id = getattr(request.state, "request_id", None) or str(uuid4())
                    return JSONResponse(
                        status_code=429,
                        content={
                            "error_code": "tenant_temporarily_throttled",
                            "message": "Tenant is temporarily throttled due to elevated error rates",
                            "trace_id": trace_id,
                        },
                    )
            except Exception:
                logger.exception("tenant_rate_limit_middleware_error")

        return await call_next(request)


class PlatformGuardrailsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        method = request.method.upper()
        path = request.url.path

        # Emergency maintenance mode: read-only except health/metrics/auth and admin controls.
        try:
            with SessionLocal() as db:
                maintenance_on = is_feature_enabled(db, key="maintenance_read_only_mode", tenant_id=None)
        except Exception:
            maintenance_on = False

        if maintenance_on and method in {"POST", "PUT", "PATCH", "DELETE"}:
            if not (path.startswith("/health") or path.startswith("/ready") or path.startswith("/metrics") or path.startswith("/auth") or path.startswith("/admin")):
                trace_id = getattr(request.state, "request_id", None) or str(uuid4())
                return JSONResponse(
                    status_code=503,
                    content={
                        "error_code": "maintenance_read_only_mode",
                        "message": "Platform is in maintenance mode (read-only)",
                        "trace_id": trace_id,
                    },
                )

        is_publish_path = path.endswith("/schedule") or path.endswith("/publish-now")
        if is_publish_path and method == "POST":
            paused_global, reason_global = is_global_publish_paused()
            if paused_global:
                trace_id = getattr(request.state, "request_id", None) or str(uuid4())
                return JSONResponse(
                    status_code=503,
                    content={
                        "error_code": "global_publish_paused",
                        "message": reason_global or "Publishing is temporarily paused globally",
                        "trace_id": trace_id,
                    },
                )
            tenant_header = request.headers.get("X-Tenant-ID")
            if tenant_header:
                try:
                    tenant_id = UUID(tenant_header)
                    paused_tenant, reason_tenant = is_tenant_publish_paused(tenant_id)
                    if paused_tenant:
                        trace_id = getattr(request.state, "request_id", None) or str(uuid4())
                        return JSONResponse(
                            status_code=429,
                            content={
                                "error_code": "tenant_publish_paused",
                                "message": reason_tenant or "Publishing is temporarily paused for tenant",
                                "trace_id": trace_id,
                            },
                        )
                except ValueError:
                    pass
        return await call_next(request)
