from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.services.audit_service import log_audit_event
from app.application.services.feature_flag_service import is_feature_enabled
from app.domain.models.brand_profile import BrandProfile
from app.domain.models.project import Project
from app.domain.models.user import User, UserRole
from app.interfaces.api.deps import get_current_user, require_roles, require_tenant_id
from app.infrastructure.db.session import get_db

router = APIRouter(prefix="/brand-profiles", tags=["brand-profiles"])


class BrandProfilePayload(BaseModel):
    project_id: UUID | None = None
    brand_name: str = Field(min_length=1, max_length=255)
    language: str = Field(default="pl", min_length=2, max_length=16)
    tone: str = Field(default="professional", min_length=2, max_length=32)
    target_audience: str | None = None
    do_list: list[str] = Field(default_factory=list)
    dont_list: list[str] = Field(default_factory=list)
    forbidden_claims: list[str] = Field(default_factory=list)
    preferred_hashtags: list[str] = Field(default_factory=list)
    compliance_notes: str | None = None


class BrandProfilePatchPayload(BaseModel):
    brand_name: str | None = Field(default=None, min_length=1, max_length=255)
    language: str | None = Field(default=None, min_length=2, max_length=16)
    tone: str | None = Field(default=None, min_length=2, max_length=32)
    target_audience: str | None = None
    do_list: list[str] | None = None
    dont_list: list[str] | None = None
    forbidden_claims: list[str] | None = None
    preferred_hashtags: list[str] | None = None
    compliance_notes: str | None = None


def _ensure_feature(db: Session, tenant_id: UUID) -> None:
    if not is_feature_enabled(db, key="v1_ai_quality_engine", tenant_id=tenant_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI quality engine disabled")


def _ensure_project_exists(db: Session, *, tenant_id: UUID, project_id: UUID | None) -> None:
    if project_id is None:
        return
    exists = db.execute(
        select(Project.id).where(Project.id == project_id, Project.company_id == tenant_id)
    ).scalar_one_or_none()
    if exists is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")


def _serialize(profile: BrandProfile) -> dict:
    return {
        "id": str(profile.id),
        "tenant_id": str(profile.company_id),
        "project_id": str(profile.project_id) if profile.project_id else None,
        "brand_name": profile.brand_name,
        "language": profile.language,
        "tone": profile.tone,
        "target_audience": profile.target_audience,
        "do_list": profile.do_list or [],
        "dont_list": profile.dont_list or [],
        "forbidden_claims": profile.forbidden_claims or [],
        "preferred_hashtags": profile.preferred_hashtags or [],
        "compliance_notes": profile.compliance_notes,
        "created_at": profile.created_at.isoformat(),
        "updated_at": profile.updated_at.isoformat(),
    }


@router.get("", status_code=status.HTTP_200_OK)
def list_brand_profiles(
    project_id: UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    tenant_id: UUID = Depends(require_tenant_id),
    current_user: User = Depends(get_current_user),
) -> dict:
    _ensure_feature(db, tenant_id)
    query = select(BrandProfile).where(BrandProfile.company_id == tenant_id)
    if project_id is not None:
        query = query.where((BrandProfile.project_id == project_id) | (BrandProfile.project_id.is_(None)))
    rows = db.execute(query.order_by(BrandProfile.project_id.is_(None).desc(), BrandProfile.updated_at.desc())).scalars().all()
    return {"items": [_serialize(row) for row in rows]}


@router.post("", status_code=status.HTTP_201_CREATED)
def create_brand_profile(
    payload: BrandProfilePayload,
    db: Session = Depends(get_db),
    tenant_id: UUID = Depends(require_tenant_id),
    current_user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER)),
) -> dict:
    _ensure_feature(db, tenant_id)
    _ensure_project_exists(db, tenant_id=tenant_id, project_id=payload.project_id)

    existing = db.execute(
        select(BrandProfile).where(
            BrandProfile.company_id == tenant_id,
            BrandProfile.project_id == payload.project_id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Brand profile already exists for scope")

    profile = BrandProfile(
        company_id=tenant_id,
        project_id=payload.project_id,
        brand_name=payload.brand_name.strip(),
        language=payload.language.strip().lower(),
        tone=payload.tone.strip().lower(),
        target_audience=payload.target_audience,
        do_list=[item.strip() for item in payload.do_list if item.strip()],
        dont_list=[item.strip() for item in payload.dont_list if item.strip()],
        forbidden_claims=[item.strip() for item in payload.forbidden_claims if item.strip()],
        preferred_hashtags=[item.strip() for item in payload.preferred_hashtags if item.strip()],
        compliance_notes=payload.compliance_notes,
    )
    db.add(profile)
    db.flush()
    log_audit_event(
        db,
        company_id=tenant_id,
        action="brand_profile.created",
        metadata={"profile_id": str(profile.id), "project_id": str(profile.project_id) if profile.project_id else None, "user_id": str(current_user.id)},
    )
    db.commit()
    db.refresh(profile)
    return _serialize(profile)


@router.patch("/{profile_id}", status_code=status.HTTP_200_OK)
def patch_brand_profile(
    profile_id: UUID,
    payload: BrandProfilePatchPayload,
    db: Session = Depends(get_db),
    tenant_id: UUID = Depends(require_tenant_id),
    current_user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER)),
) -> dict:
    _ensure_feature(db, tenant_id)
    profile = db.execute(
        select(BrandProfile).where(BrandProfile.id == profile_id, BrandProfile.company_id == tenant_id)
    ).scalar_one_or_none()
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brand profile not found")

    data = payload.model_dump(exclude_unset=True)
    if "brand_name" in data:
        profile.brand_name = data["brand_name"].strip()
    if "language" in data:
        profile.language = data["language"].strip().lower()
    if "tone" in data:
        profile.tone = data["tone"].strip().lower()
    if "target_audience" in data:
        profile.target_audience = data["target_audience"]
    if "do_list" in data:
        profile.do_list = [item.strip() for item in (data["do_list"] or []) if item.strip()]
    if "dont_list" in data:
        profile.dont_list = [item.strip() for item in (data["dont_list"] or []) if item.strip()]
    if "forbidden_claims" in data:
        profile.forbidden_claims = [item.strip() for item in (data["forbidden_claims"] or []) if item.strip()]
    if "preferred_hashtags" in data:
        profile.preferred_hashtags = [item.strip() for item in (data["preferred_hashtags"] or []) if item.strip()]
    if "compliance_notes" in data:
        profile.compliance_notes = data["compliance_notes"]

    db.add(profile)
    log_audit_event(
        db,
        company_id=tenant_id,
        action="brand_profile.updated",
        metadata={"profile_id": str(profile.id), "user_id": str(current_user.id)},
    )
    db.commit()
    db.refresh(profile)
    return _serialize(profile)


@router.delete("/{profile_id}", status_code=status.HTTP_200_OK)
def delete_brand_profile(
    profile_id: UUID,
    db: Session = Depends(get_db),
    tenant_id: UUID = Depends(require_tenant_id),
    current_user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN)),
) -> dict:
    _ensure_feature(db, tenant_id)
    profile = db.execute(
        select(BrandProfile).where(BrandProfile.id == profile_id, BrandProfile.company_id == tenant_id)
    ).scalar_one_or_none()
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brand profile not found")

    db.delete(profile)
    log_audit_event(
        db,
        company_id=tenant_id,
        action="brand_profile.deleted",
        metadata={"profile_id": str(profile_id), "user_id": str(current_user.id)},
    )
    db.commit()
    return {"deleted": True}
