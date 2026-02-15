from fastapi import APIRouter

from app.interfaces.api.auth import router as auth_router
from app.interfaces.api.channels import router as channels_router
from app.interfaces.api.health import router as health_router
from app.interfaces.api.posts import router as posts_router
from app.interfaces.api.projects import router as projects_router
from app.interfaces.api.signup import router as signup_router
from app.interfaces.api.tenant import router as tenant_router
from app.interfaces.api.website_publications import router as website_publications_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["health"])
api_router.include_router(tenant_router)
api_router.include_router(auth_router)
api_router.include_router(signup_router)
api_router.include_router(projects_router)
api_router.include_router(channels_router)
api_router.include_router(posts_router)
api_router.include_router(website_publications_router)
