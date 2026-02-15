from uuid import UUID, uuid4

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.core.tenant import reset_current_tenant, set_current_tenant


class TenantContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        tenant_header = request.headers.get("X-Tenant-ID")
        token = None

        if tenant_header:
            try:
                tenant_id = UUID(tenant_header)
                token = set_current_tenant(tenant_id)
            except ValueError:
                return JSONResponse(status_code=400, content={"detail": "Invalid X-Tenant-ID header"})

        try:
            response = await call_next(request)
            return response
        finally:
            if token is not None:
                reset_current_tenant(token)


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
