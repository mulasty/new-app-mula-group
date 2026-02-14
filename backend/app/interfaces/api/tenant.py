from fastapi import APIRouter

from app.core.tenant import get_current_tenant

router = APIRouter(prefix="/tenant", tags=["tenant"])


@router.get("/context")
def tenant_context() -> dict:
    tenant_id = get_current_tenant()
    return {"tenant_id": str(tenant_id) if tenant_id else None}
