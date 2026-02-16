from fastapi import APIRouter

from app.interfaces.api.analytics import router as analytics_router
from app.interfaces.api.ai_quality import router as ai_quality_router
from app.interfaces.api.admin import router as admin_router
from app.interfaces.api.automation import router as automation_router
from app.interfaces.api.auth import router as auth_router
from app.interfaces.api.billing import public_router as public_billing_router
from app.interfaces.api.billing import router as billing_router
from app.interfaces.api.channels import router as channels_router
from app.interfaces.api.connectors import router as connectors_router
from app.interfaces.api.feature_flags import router as feature_flags_router
from app.interfaces.api.health import router as health_router
from app.interfaces.api.posts import router as posts_router
from app.interfaces.api.projects import router as projects_router
from app.interfaces.api.signup import router as signup_router
from app.interfaces.api.stripe_webhooks import router as stripe_webhooks_router
from app.interfaces.api.system_ops import router as system_ops_router
from app.interfaces.api.tenant import router as tenant_router
from app.interfaces.api.website_publications import router as website_publications_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["health"])
api_router.include_router(tenant_router)
api_router.include_router(auth_router)
api_router.include_router(signup_router)
api_router.include_router(public_billing_router)
api_router.include_router(stripe_webhooks_router)
api_router.include_router(feature_flags_router)
api_router.include_router(billing_router)
api_router.include_router(projects_router)
api_router.include_router(channels_router)
api_router.include_router(connectors_router)
api_router.include_router(posts_router)
api_router.include_router(analytics_router)
api_router.include_router(automation_router)
api_router.include_router(ai_quality_router)
api_router.include_router(admin_router)
api_router.include_router(system_ops_router)
api_router.include_router(website_publications_router)
