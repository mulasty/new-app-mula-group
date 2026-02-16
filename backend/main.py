import logging
import logging.config
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.domain import models  # noqa: F401
from app.interfaces.api.router import api_router
from app.interfaces.http.middleware import (
    MetricsMiddleware,
    PlanEnforcementMiddleware,
    RequestIDMiddleware,
    SecurityHeadersMiddleware,
    TenantContextMiddleware,
    TenantRateLimitMiddleware,
)

logging_config_path = Path(__file__).with_name("logging.json")
if logging_config_path.exists():
    logging.config.dictConfig(json.loads(logging_config_path.read_text(encoding="utf-8")))
else:
    logging.basicConfig(level=logging.INFO)

logger = logging.getLogger("app")

app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(TenantContextMiddleware)
app.add_middleware(PlanEnforcementMiddleware)
app.add_middleware(TenantRateLimitMiddleware, requests_per_minute=settings.tenant_rate_limit_per_minute)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(MetricsMiddleware)


def _error_payload(*, request: Request, error_code: str, message: str) -> dict:
    trace_id = getattr(request.state, "request_id", None)
    return {
        "error_code": error_code,
        "message": message,
        "trace_id": trace_id,
    }


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    if isinstance(exc.detail, dict) and "error_code" in exc.detail and "message" in exc.detail:
        error_code = str(exc.detail["error_code"])
        detail = str(exc.detail["message"])
    else:
        error_code = str(exc.status_code)
        detail = exc.detail if isinstance(exc.detail, str) else "Request failed"
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_payload(request=request, error_code=error_code, message=detail),
    )


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=_error_payload(
            request=request,
            error_code="validation_error",
            message="Request validation failed",
        ),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled_exception path=%s method=%s", request.url.path, request.method)
    return JSONResponse(
        status_code=500,
        content=_error_payload(
            request=request,
            error_code="internal_server_error",
            message="Internal server error",
        ),
    )

app.include_router(api_router)
