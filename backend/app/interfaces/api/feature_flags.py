from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.services.feature_flag_service import (
    bootstrap_feature_flags,
    invalidate_feature_flags_cache,
    list_feature_flags,
)
from app.domain.models.feature_flag import FeatureFlag
from app.domain.models.user import User, UserRole
from app.interfaces.api.deps import get_current_user, require_roles, require_tenant_id
from app.infrastructure.db.session import get_db

router = APIRouter(prefix="/feature-flags", tags=["feature-flags"])


class FeatureFlagPatchRequest(BaseModel):
    enabled_globally: bool | None = None
    enabled_for_tenant: bool | None = None


@router.get("", status_code=status.HTTP_200_OK)
def get_feature_flags(
    db: Session = Depends(get_db),
    tenant_id: UUID = Depends(require_tenant_id),
    current_user: User = Depends(get_current_user),
) -> dict:
    bootstrap_feature_flags(db)
    db.commit()
    return {"items": list_feature_flags(db, tenant_id=tenant_id)}


@router.patch("/{flag_id}", status_code=status.HTTP_200_OK)
def patch_feature_flag(
    flag_id: UUID,
    payload: FeatureFlagPatchRequest,
    db: Session = Depends(get_db),
    tenant_id: UUID = Depends(require_tenant_id),
    current_user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN)),
) -> dict:
    flag = db.execute(select(FeatureFlag).where(FeatureFlag.id == flag_id)).scalar_one_or_none()
    if flag is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feature flag not found")

    if payload.enabled_globally is not None:
        flag.enabled_globally = payload.enabled_globally
    if payload.enabled_for_tenant is not None:
        mapping = dict(flag.enabled_per_tenant or {})
        mapping[str(tenant_id)] = payload.enabled_for_tenant
        flag.enabled_per_tenant = mapping

    db.add(flag)
    db.commit()
    invalidate_feature_flags_cache()
    flags = list_feature_flags(db, tenant_id=tenant_id)
    updated = next((item for item in flags if item["id"] == str(flag.id)), None)
    return {"item": updated, "items": flags}
