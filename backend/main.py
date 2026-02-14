from fastapi import FastAPI

from app.core.config import settings
from app.domain import models  # noqa: F401
from app.interfaces.api.router import api_router
from app.interfaces.http.middleware import TenantContextMiddleware

app = FastAPI(title=settings.app_name)
app.add_middleware(TenantContextMiddleware)
app.include_router(api_router)
