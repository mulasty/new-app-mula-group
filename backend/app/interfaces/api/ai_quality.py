from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.services.ai_quality_service import (
    apply_quality_to_content_metadata,
    evaluate_text,
    get_or_create_policy,
)
from app.application.services.audit_service import log_audit_event
from app.application.services.feature_flag_service import is_feature_enabled
from app.domain.models.content_item import ContentItem
from app.domain.models.project import Project
from app.domain.models.user import User, UserRole
from app.interfaces.api.deps import get_current_user, require_roles, require_tenant_id
from app.infrastructure.db.session import get_db

router = APIRouter(prefix="/ai-quality", tags=["ai-quality"])


def _ensure_ai_quality_enabled(db: Session, tenant_id: UUID) -> None:
    if not is_feature_enabled(db, key="beta_ai_quality", tenant_id=tenant_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI quality feature is disabled")


class EvaluateRequest(BaseModel):
    project_id: UUID
    title: str | None = Field(default=None, max_length=255)
    body: str = Field(min_length=1)


class PolicyPatchRequest(BaseModel):
    policy_json: dict


class VariantRequest(BaseModel):
    project_id: UUID
    body: str = Field(min_length=1)
    count: int = Field(default=2, ge=2, le=5)


def _ensure_project(db: Session, *, tenant_id: UUID, project_id: UUID) -> None:
    exists = db.execute(
        select(Project.id).where(Project.id == project_id, Project.company_id == tenant_id)
    ).scalar_one_or_none()
    if exists is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")


@router.get("/policy", status_code=status.HTTP_200_OK)
def get_policy(
    project_id: UUID = Query(...),
    db: Session = Depends(get_db),
    tenant_id: UUID = Depends(require_tenant_id),
    current_user: User = Depends(get_current_user),
) -> dict:
    _ensure_ai_quality_enabled(db, tenant_id)
    _ensure_project(db, tenant_id=tenant_id, project_id=project_id)
    policy = get_or_create_policy(db, company_id=tenant_id, project_id=project_id)
    db.commit()
    return {"id": str(policy.id), "project_id": str(policy.project_id), "policy_json": policy.policy_json or {}}


@router.patch("/policy", status_code=status.HTTP_200_OK)
def patch_policy(
    payload: PolicyPatchRequest,
    project_id: UUID = Query(...),
    db: Session = Depends(get_db),
    tenant_id: UUID = Depends(require_tenant_id),
    current_user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER)),
) -> dict:
    _ensure_ai_quality_enabled(db, tenant_id)
    _ensure_project(db, tenant_id=tenant_id, project_id=project_id)
    policy = get_or_create_policy(
        db,
        company_id=tenant_id,
        project_id=project_id,
        created_by_user_id=current_user.id,
    )
    policy.policy_json = payload.policy_json or {}
    db.add(policy)
    log_audit_event(
        db,
        company_id=tenant_id,
        action="ai_quality.policy_updated",
        metadata={"project_id": str(project_id), "user_id": str(current_user.id)},
    )
    db.commit()
    return {"id": str(policy.id), "project_id": str(policy.project_id), "policy_json": policy.policy_json}


@router.post("/evaluate", status_code=status.HTTP_200_OK)
def evaluate_content(
    payload: EvaluateRequest,
    db: Session = Depends(get_db),
    tenant_id: UUID = Depends(require_tenant_id),
    current_user: User = Depends(get_current_user),
) -> dict:
    _ensure_ai_quality_enabled(db, tenant_id)
    _ensure_project(db, tenant_id=tenant_id, project_id=payload.project_id)
    policy = get_or_create_policy(db, company_id=tenant_id, project_id=payload.project_id)
    db.commit()
    evaluation = evaluate_text(text=payload.body, title=payload.title, policy_json=policy.policy_json)
    return {
        "risk_score": evaluation.risk_score,
        "tone_score": evaluation.tone_score,
        "risk_flags": evaluation.risk_flags,
        "needs_approval": evaluation.needs_approval,
        "metadata": evaluation.metadata,
    }


@router.post("/variants", status_code=status.HTTP_200_OK)
def generate_variants(
    payload: VariantRequest,
    db: Session = Depends(get_db),
    tenant_id: UUID = Depends(require_tenant_id),
    current_user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER, UserRole.EDITOR)),
) -> dict:
    _ensure_ai_quality_enabled(db, tenant_id)
    _ensure_project(db, tenant_id=tenant_id, project_id=payload.project_id)
    base = payload.body.strip()
    variants = [
        {"label": "A", "body": base},
        {"label": "B", "body": f"{base}\n\nSprawdz szczegoly na naszej stronie."},
    ]
    if payload.count > 2:
        variants.append({"label": "C", "body": f"{base}\n\nPodziel sie opinia w komentarzu."})
    return {"items": variants[: payload.count]}


@router.post("/content/{content_id}/evaluate-and-attach", status_code=status.HTTP_200_OK)
def evaluate_existing_content(
    content_id: UUID,
    db: Session = Depends(get_db),
    tenant_id: UUID = Depends(require_tenant_id),
    current_user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER, UserRole.EDITOR)),
) -> dict:
    _ensure_ai_quality_enabled(db, tenant_id)
    item = db.execute(
        select(ContentItem).where(ContentItem.id == content_id, ContentItem.company_id == tenant_id)
    ).scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Content item not found")
    policy = get_or_create_policy(db, company_id=tenant_id, project_id=item.project_id)
    evaluation = evaluate_text(text=item.body, title=item.title, policy_json=policy.policy_json)
    item.metadata_json = apply_quality_to_content_metadata(metadata_json=item.metadata_json, evaluation=evaluation)
    if evaluation.needs_approval and item.status not in {"approved", "published", "scheduled"}:
        item.status = "needs_review"
    db.add(item)
    db.commit()
    return {"id": str(item.id), "status": item.status, "quality": item.metadata_json.get("quality", {})}
