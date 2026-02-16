from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.services.automation_service import create_automation_run, enqueue_automation_run
from app.application.services.feature_flag_service import is_feature_enabled
from app.application.services.publishing_service import emit_publish_event
from app.domain.models.approval import Approval, ApprovalStatus
from app.domain.models.automation_event import AutomationEvent
from app.domain.models.automation_rule import (
    AutomationActionType,
    AutomationRule,
    AutomationTriggerType,
)
from app.domain.models.automation_run import AutomationRun
from app.domain.models.campaign import Campaign, CampaignStatus
from app.domain.models.content_item import ContentItem, ContentItemSource, ContentItemStatus
from app.domain.models.content_template import ContentTemplate, ContentTemplateType
from app.domain.models.post import Post, PostStatus
from app.domain.models.project import Project
from app.domain.models.user import User, UserRole
from app.interfaces.api.deps import get_current_user, require_roles, require_tenant_id
from app.infrastructure.db.session import get_db

router = APIRouter(tags=["automation"])

TEMPLATE_CATEGORIES = {"product launch", "educational", "social proof", "engagement", "promotional"}


def _serialize_campaign(item: Campaign) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "company_id": str(item.company_id),
        "project_id": str(item.project_id),
        "name": item.name,
        "description": item.description,
        "status": item.status,
        "timezone": item.timezone,
        "language": item.language,
        "brand_profile_json": item.brand_profile_json or {},
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
    }


def _serialize_template(item: ContentTemplate) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "company_id": str(item.company_id),
        "project_id": str(item.project_id),
        "name": item.name,
        "category": item.category,
        "tone": item.tone,
        "content_structure": item.content_structure,
        "template_type": item.template_type,
        "prompt_template": item.prompt_template,
        "output_schema_json": item.output_schema_json or {},
        "default_values_json": item.default_values_json or {},
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
    }


def _serialize_rule(item: AutomationRule) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "company_id": str(item.company_id),
        "project_id": str(item.project_id),
        "campaign_id": str(item.campaign_id) if item.campaign_id else None,
        "name": item.name,
        "is_enabled": item.is_enabled,
        "trigger_type": item.trigger_type,
        "trigger_config_json": item.trigger_config_json or {},
        "action_type": item.action_type,
        "action_config_json": item.action_config_json or {},
        "guardrails_json": item.guardrails_json or {},
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
    }


def _serialize_content(item: ContentItem) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "company_id": str(item.company_id),
        "project_id": str(item.project_id),
        "campaign_id": str(item.campaign_id) if item.campaign_id else None,
        "template_id": str(item.template_id) if item.template_id else None,
        "status": item.status,
        "title": item.title,
        "body": item.body,
        "metadata_json": item.metadata_json or {},
        "source": item.source,
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
    }


def _serialize_run(item: AutomationRun) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "company_id": str(item.company_id),
        "project_id": str(item.project_id),
        "rule_id": str(item.rule_id),
        "status": item.status,
        "started_at": item.started_at.isoformat() if item.started_at else None,
        "finished_at": item.finished_at.isoformat() if item.finished_at else None,
        "error_message": item.error_message,
        "stats_json": item.stats_json or {},
        "created_at": item.created_at.isoformat(),
    }


def _serialize_automation_event(item: AutomationEvent) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "company_id": str(item.company_id),
        "project_id": str(item.project_id),
        "run_id": str(item.run_id),
        "event_type": item.event_type,
        "status": item.status,
        "metadata_json": item.metadata_json or {},
        "created_at": item.created_at.isoformat(),
    }


def _ensure_project_access(db: Session, *, tenant_id: UUID, project_id: UUID) -> None:
    project_exists = db.execute(
        select(Project.id).where(Project.id == project_id, Project.company_id == tenant_id)
    ).scalar_one_or_none()
    if project_exists is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")


class CampaignCreateRequest(BaseModel):
    project_id: UUID
    name: str = Field(min_length=2, max_length=255)
    description: str | None = None
    timezone: str = Field(default="Europe/Warsaw", min_length=2, max_length=64)
    language: str = Field(default="pl", min_length=2, max_length=16)
    brand_profile_json: dict[str, Any] = Field(default_factory=dict)


class CampaignPatchRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    description: str | None = None
    timezone: str | None = Field(default=None, min_length=2, max_length=64)
    language: str | None = Field(default=None, min_length=2, max_length=16)
    brand_profile_json: dict[str, Any] | None = None
    status: str | None = None


class TemplateCreateRequest(BaseModel):
    project_id: UUID
    name: str = Field(min_length=2, max_length=255)
    category: str = Field(default="educational", min_length=2, max_length=64)
    tone: str = Field(default="professional", min_length=2, max_length=64)
    content_structure: str = Field(default="", max_length=2000)
    template_type: str = Field(default=ContentTemplateType.POST_TEXT.value)
    prompt_template: str = Field(min_length=10)
    output_schema_json: dict[str, Any] = Field(default_factory=dict)
    default_values_json: dict[str, Any] = Field(default_factory=dict)


class TemplatePatchRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    category: str | None = Field(default=None, min_length=2, max_length=64)
    tone: str | None = Field(default=None, min_length=2, max_length=64)
    content_structure: str | None = Field(default=None, max_length=2000)
    template_type: str | None = None
    prompt_template: str | None = Field(default=None, min_length=10)
    output_schema_json: dict[str, Any] | None = None
    default_values_json: dict[str, Any] | None = None


class RuleCreateRequest(BaseModel):
    project_id: UUID
    campaign_id: UUID | None = None
    name: str = Field(min_length=2, max_length=255)
    is_enabled: bool = True
    trigger_type: str
    trigger_config_json: dict[str, Any] = Field(default_factory=dict)
    action_type: str
    action_config_json: dict[str, Any] = Field(default_factory=dict)
    guardrails_json: dict[str, Any] = Field(default_factory=dict)


class RulePatchRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    is_enabled: bool | None = None
    trigger_type: str | None = None
    trigger_config_json: dict[str, Any] | None = None
    action_type: str | None = None
    action_config_json: dict[str, Any] | None = None
    guardrails_json: dict[str, Any] | None = None
    campaign_id: UUID | None = None


class ContentCreateRequest(BaseModel):
    project_id: UUID
    campaign_id: UUID | None = None
    template_id: UUID | None = None
    title: str | None = Field(default=None, max_length=255)
    body: str = Field(min_length=1)
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    status: str = Field(default=ContentItemStatus.DRAFT.value)


class ContentReviewRequest(BaseModel):
    comment: str | None = None


class ContentScheduleRequest(BaseModel):
    publish_at: datetime


def _create_default_templates(db: Session, *, tenant_id: UUID, project_id: UUID) -> None:
    existing = db.execute(
        select(ContentTemplate.id).where(
            ContentTemplate.company_id == tenant_id,
            ContentTemplate.project_id == project_id,
        )
    ).first()
    if existing is not None:
        return

    defaults = [
        (
            "Product launch template",
            "product launch",
            "bold",
            "Hook -> key benefit -> social proof -> CTA",
            "Opisz premierę produktu {{project_name}} i zachęć do działania: {{cta}}.",
        ),
        (
            "Educational template",
            "educational",
            "expert",
            "Problem -> insight -> practical tip -> CTA",
            "Stwórz edukacyjny post o {{topic}} dla projektu {{project_name}}.",
        ),
        (
            "Social proof template",
            "social proof",
            "trustworthy",
            "Result -> quote -> impact -> CTA",
            "Stwórz post social proof z referencją klienta i CTA: {{cta}}.",
        ),
        (
            "Engagement template",
            "engagement",
            "friendly",
            "Question -> short context -> call for comments",
            "Napisz angażujący post z pytaniem otwartym o {{topic}}.",
        ),
        (
            "Promotional template",
            "promotional",
            "persuasive",
            "Offer -> urgency -> value -> CTA",
            "Napisz post promocyjny dla {{project_name}} z ofertą {{offer}}.",
        ),
    ]

    for name, category, tone, content_structure, prompt in defaults:
        db.add(
            ContentTemplate(
                company_id=tenant_id,
                project_id=project_id,
                name=name,
                category=category,
                tone=tone,
                content_structure=content_structure,
                template_type=ContentTemplateType.POST_TEXT.value,
                prompt_template=prompt,
                output_schema_json={
                    "type": "object",
                    "required": ["title", "body", "hashtags", "cta", "channels", "risk_flags"],
                },
                default_values_json={},
            )
        )


@router.post("/campaigns", status_code=status.HTTP_201_CREATED)
def create_campaign(
    payload: CampaignCreateRequest,
    db: Session = Depends(get_db),
    tenant_id: UUID = Depends(require_tenant_id),
    current_user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER)),
) -> dict[str, Any]:
    _ensure_project_access(db, tenant_id=tenant_id, project_id=payload.project_id)
    campaign = Campaign(
        company_id=tenant_id,
        project_id=payload.project_id,
        name=payload.name.strip(),
        description=(payload.description.strip() if payload.description else None),
        status=CampaignStatus.DRAFT.value,
        timezone=payload.timezone.strip(),
        language=payload.language.strip(),
        brand_profile_json=payload.brand_profile_json or {},
    )
    db.add(campaign)
    db.commit()
    db.refresh(campaign)
    return _serialize_campaign(campaign)


@router.get("/campaigns", status_code=status.HTTP_200_OK)
def list_campaigns(
    project_id: UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    tenant_id: UUID = Depends(require_tenant_id),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    query = select(Campaign).where(Campaign.company_id == tenant_id)
    if project_id is not None:
        query = query.where(Campaign.project_id == project_id)
    rows = db.execute(query.order_by(Campaign.created_at.desc())).scalars().all()
    return {"items": [_serialize_campaign(item) for item in rows]}


@router.patch("/campaigns/{campaign_id}", status_code=status.HTTP_200_OK)
def patch_campaign(
    campaign_id: UUID,
    payload: CampaignPatchRequest,
    db: Session = Depends(get_db),
    tenant_id: UUID = Depends(require_tenant_id),
    current_user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER)),
) -> dict[str, Any]:
    campaign = db.execute(
        select(Campaign).where(Campaign.id == campaign_id, Campaign.company_id == tenant_id)
    ).scalar_one_or_none()
    if campaign is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    if payload.name is not None:
        campaign.name = payload.name.strip()
    if payload.description is not None:
        campaign.description = payload.description.strip() if payload.description else None
    if payload.timezone is not None:
        campaign.timezone = payload.timezone.strip()
    if payload.language is not None:
        campaign.language = payload.language.strip()
    if payload.brand_profile_json is not None:
        campaign.brand_profile_json = payload.brand_profile_json
    if payload.status is not None:
        if payload.status not in [status_value.value for status_value in CampaignStatus]:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid campaign status")
        campaign.status = payload.status
    db.add(campaign)
    db.commit()
    db.refresh(campaign)
    return _serialize_campaign(campaign)


@router.post("/campaigns/{campaign_id}/activate", status_code=status.HTTP_200_OK)
def activate_campaign(
    campaign_id: UUID,
    db: Session = Depends(get_db),
    tenant_id: UUID = Depends(require_tenant_id),
    current_user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER)),
) -> dict[str, Any]:
    campaign = db.execute(
        select(Campaign).where(Campaign.id == campaign_id, Campaign.company_id == tenant_id)
    ).scalar_one_or_none()
    if campaign is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    campaign.status = CampaignStatus.ACTIVE.value
    db.add(campaign)
    db.commit()
    db.refresh(campaign)
    return _serialize_campaign(campaign)


@router.post("/campaigns/{campaign_id}/pause", status_code=status.HTTP_200_OK)
def pause_campaign(
    campaign_id: UUID,
    db: Session = Depends(get_db),
    tenant_id: UUID = Depends(require_tenant_id),
    current_user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER)),
) -> dict[str, Any]:
    campaign = db.execute(
        select(Campaign).where(Campaign.id == campaign_id, Campaign.company_id == tenant_id)
    ).scalar_one_or_none()
    if campaign is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    campaign.status = CampaignStatus.PAUSED.value
    db.add(campaign)
    db.commit()
    db.refresh(campaign)
    return _serialize_campaign(campaign)


@router.post("/templates", status_code=status.HTTP_201_CREATED)
def create_template(
    payload: TemplateCreateRequest,
    db: Session = Depends(get_db),
    tenant_id: UUID = Depends(require_tenant_id),
    current_user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER, UserRole.EDITOR)),
) -> dict[str, Any]:
    _ensure_project_access(db, tenant_id=tenant_id, project_id=payload.project_id)
    if payload.template_type not in [item.value for item in ContentTemplateType]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid template type")
    if payload.category.strip().lower() not in TEMPLATE_CATEGORIES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid template category")
    template = ContentTemplate(
        company_id=tenant_id,
        project_id=payload.project_id,
        name=payload.name.strip(),
        category=payload.category.strip().lower(),
        tone=payload.tone.strip(),
        content_structure=payload.content_structure.strip(),
        template_type=payload.template_type,
        prompt_template=payload.prompt_template,
        output_schema_json=payload.output_schema_json or {},
        default_values_json=payload.default_values_json or {},
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    return _serialize_template(template)


@router.get("/templates", status_code=status.HTTP_200_OK)
def list_templates(
    project_id: UUID | None = Query(default=None),
    category: str | None = Query(default=None),
    db: Session = Depends(get_db),
    tenant_id: UUID = Depends(require_tenant_id),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    if (
        project_id is not None
        and is_feature_enabled(db, key="v1_template_library", tenant_id=tenant_id)
    ):
        _create_default_templates(db, tenant_id=tenant_id, project_id=project_id)
        db.commit()

    query = select(ContentTemplate).where(ContentTemplate.company_id == tenant_id)
    if project_id is not None:
        query = query.where(ContentTemplate.project_id == project_id)
    if category is not None:
        query = query.where(ContentTemplate.category == category.strip().lower())
    rows = db.execute(query.order_by(ContentTemplate.created_at.desc())).scalars().all()
    return {"items": [_serialize_template(item) for item in rows]}


@router.patch("/templates/{template_id}", status_code=status.HTTP_200_OK)
def patch_template(
    template_id: UUID,
    payload: TemplatePatchRequest,
    db: Session = Depends(get_db),
    tenant_id: UUID = Depends(require_tenant_id),
    current_user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER, UserRole.EDITOR)),
) -> dict[str, Any]:
    template = db.execute(
        select(ContentTemplate).where(ContentTemplate.id == template_id, ContentTemplate.company_id == tenant_id)
    ).scalar_one_or_none()
    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    if payload.name is not None:
        template.name = payload.name.strip()
    if payload.category is not None:
        next_category = payload.category.strip().lower()
        if next_category not in TEMPLATE_CATEGORIES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid template category")
        template.category = next_category
    if payload.tone is not None:
        template.tone = payload.tone.strip()
    if payload.content_structure is not None:
        template.content_structure = payload.content_structure.strip()
    if payload.template_type is not None:
        if payload.template_type not in [item.value for item in ContentTemplateType]:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid template type")
        template.template_type = payload.template_type
    if payload.prompt_template is not None:
        template.prompt_template = payload.prompt_template
    if payload.output_schema_json is not None:
        template.output_schema_json = payload.output_schema_json
    if payload.default_values_json is not None:
        template.default_values_json = payload.default_values_json
    db.add(template)
    db.commit()
    db.refresh(template)
    return _serialize_template(template)


@router.post("/automation/rules", status_code=status.HTTP_201_CREATED)
def create_rule(
    payload: RuleCreateRequest,
    db: Session = Depends(get_db),
    tenant_id: UUID = Depends(require_tenant_id),
    current_user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER)),
) -> dict[str, Any]:
    _ensure_project_access(db, tenant_id=tenant_id, project_id=payload.project_id)
    if payload.trigger_type not in [item.value for item in AutomationTriggerType]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid trigger type")
    if payload.action_type not in [item.value for item in AutomationActionType]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid action type")
    campaign_id = payload.campaign_id
    if campaign_id is not None:
        campaign = db.execute(
            select(Campaign).where(
                Campaign.id == campaign_id,
                Campaign.company_id == tenant_id,
                Campaign.project_id == payload.project_id,
            )
        ).scalar_one_or_none()
        if campaign is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    rule = AutomationRule(
        company_id=tenant_id,
        project_id=payload.project_id,
        campaign_id=campaign_id,
        name=payload.name.strip(),
        is_enabled=payload.is_enabled,
        trigger_type=payload.trigger_type,
        trigger_config_json=payload.trigger_config_json or {},
        action_type=payload.action_type,
        action_config_json=payload.action_config_json or {},
        guardrails_json=payload.guardrails_json or {},
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return _serialize_rule(rule)


@router.get("/automation/rules", status_code=status.HTTP_200_OK)
def list_rules(
    project_id: UUID | None = Query(default=None),
    campaign_id: UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    tenant_id: UUID = Depends(require_tenant_id),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    query = select(AutomationRule).where(AutomationRule.company_id == tenant_id)
    if project_id is not None:
        query = query.where(AutomationRule.project_id == project_id)
    if campaign_id is not None:
        query = query.where(AutomationRule.campaign_id == campaign_id)
    rows = db.execute(query.order_by(AutomationRule.created_at.desc())).scalars().all()
    return {"items": [_serialize_rule(item) for item in rows]}


@router.patch("/automation/rules/{rule_id}", status_code=status.HTTP_200_OK)
def patch_rule(
    rule_id: UUID,
    payload: RulePatchRequest,
    db: Session = Depends(get_db),
    tenant_id: UUID = Depends(require_tenant_id),
    current_user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER)),
) -> dict[str, Any]:
    rule = db.execute(
        select(AutomationRule).where(AutomationRule.id == rule_id, AutomationRule.company_id == tenant_id)
    ).scalar_one_or_none()
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")
    if payload.name is not None:
        rule.name = payload.name.strip()
    if payload.is_enabled is not None:
        rule.is_enabled = payload.is_enabled
    if payload.trigger_type is not None:
        if payload.trigger_type not in [item.value for item in AutomationTriggerType]:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid trigger type")
        rule.trigger_type = payload.trigger_type
    if payload.action_type is not None:
        if payload.action_type not in [item.value for item in AutomationActionType]:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid action type")
        rule.action_type = payload.action_type
    if payload.trigger_config_json is not None:
        rule.trigger_config_json = payload.trigger_config_json
    if payload.action_config_json is not None:
        rule.action_config_json = payload.action_config_json
    if payload.guardrails_json is not None:
        rule.guardrails_json = payload.guardrails_json
    if payload.campaign_id is not None:
        if payload.campaign_id:
            campaign = db.execute(
                select(Campaign).where(
                    Campaign.id == payload.campaign_id,
                    Campaign.company_id == tenant_id,
                    Campaign.project_id == rule.project_id,
                )
            ).scalar_one_or_none()
            if campaign is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
        rule.campaign_id = payload.campaign_id
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return _serialize_rule(rule)


@router.post("/automation/rules/{rule_id}/run-now", status_code=status.HTTP_202_ACCEPTED)
def run_rule_now(
    rule_id: UUID,
    db: Session = Depends(get_db),
    tenant_id: UUID = Depends(require_tenant_id),
    current_user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER)),
) -> dict[str, Any]:
    rule = db.execute(
        select(AutomationRule).where(AutomationRule.id == rule_id, AutomationRule.company_id == tenant_id)
    ).scalar_one_or_none()
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")
    try:
        run = create_automation_run(
            db,
            rule=rule,
            trigger_reason="manual_run_now",
            trigger_metadata={"requested_by": str(current_user.id)},
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Rule has recent run and cannot be enqueued yet",
        )
    db.commit()
    enqueue_automation_run(run.id)
    return {"run_id": str(run.id), "status": "queued"}


@router.get("/content", status_code=status.HTTP_200_OK)
def list_content(
    project_id: UUID | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    tenant_id: UUID = Depends(require_tenant_id),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    query = select(ContentItem).where(ContentItem.company_id == tenant_id)
    if project_id is not None:
        query = query.where(ContentItem.project_id == project_id)
    if status_filter is not None:
        query = query.where(ContentItem.status == status_filter)
    rows = db.execute(query.order_by(ContentItem.created_at.desc())).scalars().all()
    return {"items": [_serialize_content(item) for item in rows]}


@router.post("/content", status_code=status.HTTP_201_CREATED)
def create_content(
    payload: ContentCreateRequest,
    db: Session = Depends(get_db),
    tenant_id: UUID = Depends(require_tenant_id),
    current_user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER, UserRole.EDITOR)),
) -> dict[str, Any]:
    _ensure_project_access(db, tenant_id=tenant_id, project_id=payload.project_id)
    if payload.status not in [item.value for item in ContentItemStatus]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid content status")
    item = ContentItem(
        company_id=tenant_id,
        project_id=payload.project_id,
        campaign_id=payload.campaign_id,
        template_id=payload.template_id,
        status=payload.status,
        title=payload.title.strip() if payload.title else None,
        body=payload.body,
        metadata_json=payload.metadata_json or {},
        source=ContentItemSource.MANUAL.value,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return _serialize_content(item)


@router.post("/content/{content_id}/approve", status_code=status.HTTP_200_OK)
def approve_content(
    content_id: UUID,
    payload: ContentReviewRequest,
    db: Session = Depends(get_db),
    tenant_id: UUID = Depends(require_tenant_id),
    current_user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER)),
) -> dict[str, Any]:
    item = db.execute(
        select(ContentItem).where(ContentItem.id == content_id, ContentItem.company_id == tenant_id)
    ).scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Content item not found")
    item.status = ContentItemStatus.APPROVED.value
    approval = Approval(
        company_id=tenant_id,
        project_id=item.project_id,
        content_item_id=item.id,
        requested_by_user_id=current_user.id,
        reviewed_by_user_id=current_user.id,
        status=ApprovalStatus.APPROVED.value,
        comment=payload.comment,
    )
    db.add(item)
    db.add(approval)
    db.commit()
    db.refresh(item)
    return _serialize_content(item)


@router.post("/content/{content_id}/reject", status_code=status.HTTP_200_OK)
def reject_content(
    content_id: UUID,
    payload: ContentReviewRequest,
    db: Session = Depends(get_db),
    tenant_id: UUID = Depends(require_tenant_id),
    current_user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER)),
) -> dict[str, Any]:
    item = db.execute(
        select(ContentItem).where(ContentItem.id == content_id, ContentItem.company_id == tenant_id)
    ).scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Content item not found")
    item.status = ContentItemStatus.REJECTED.value
    approval = Approval(
        company_id=tenant_id,
        project_id=item.project_id,
        content_item_id=item.id,
        requested_by_user_id=current_user.id,
        reviewed_by_user_id=current_user.id,
        status=ApprovalStatus.REJECTED.value,
        comment=payload.comment,
    )
    db.add(item)
    db.add(approval)
    db.commit()
    db.refresh(item)
    return _serialize_content(item)


@router.post("/content/{content_id}/schedule", status_code=status.HTTP_200_OK)
def schedule_content(
    content_id: UUID,
    payload: ContentScheduleRequest,
    db: Session = Depends(get_db),
    tenant_id: UUID = Depends(require_tenant_id),
    current_user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER)),
) -> dict[str, Any]:
    item = db.execute(
        select(ContentItem).where(ContentItem.id == content_id, ContentItem.company_id == tenant_id)
    ).scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Content item not found")
    publish_at = payload.publish_at if payload.publish_at.tzinfo else payload.publish_at.replace(tzinfo=UTC)
    post = Post(
        company_id=tenant_id,
        project_id=item.project_id,
        title=item.title or "Scheduled content",
        content=item.body,
        status=PostStatus.SCHEDULED.value,
        publish_at=publish_at,
    )
    db.add(post)
    db.flush()
    item.status = ContentItemStatus.SCHEDULED.value
    item.metadata_json = {**(item.metadata_json or {}), "scheduled_post_id": str(post.id), "scheduled_for": publish_at.isoformat()}
    emit_publish_event(
        db,
        company_id=post.company_id,
        project_id=post.project_id,
        post_id=post.id,
        event_type="PostScheduled",
        status="ok",
        metadata_json={"source": "content_schedule", "content_item_id": str(item.id)},
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return {
        "content_item": _serialize_content(item),
        "post_id": str(post.id),
    }


@router.get("/automation/runs", status_code=status.HTTP_200_OK)
def list_runs(
    project_id: UUID | None = Query(default=None),
    rule_id: UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    tenant_id: UUID = Depends(require_tenant_id),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    query = select(AutomationRun).where(AutomationRun.company_id == tenant_id)
    if project_id is not None:
        query = query.where(AutomationRun.project_id == project_id)
    if rule_id is not None:
        query = query.where(AutomationRun.rule_id == rule_id)
    rows = db.execute(query.order_by(AutomationRun.created_at.desc())).scalars().all()
    return {"items": [_serialize_run(item) for item in rows]}


@router.get("/automation/runs/{run_id}/events", status_code=status.HTTP_200_OK)
def list_run_events(
    run_id: UUID,
    db: Session = Depends(get_db),
    tenant_id: UUID = Depends(require_tenant_id),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    run_exists = db.execute(
        select(AutomationRun.id).where(AutomationRun.id == run_id, AutomationRun.company_id == tenant_id)
    ).scalar_one_or_none()
    if run_exists is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Automation run not found")
    rows = db.execute(
        select(AutomationEvent)
        .where(AutomationEvent.run_id == run_id, AutomationEvent.company_id == tenant_id)
        .order_by(AutomationEvent.created_at.desc())
    ).scalars().all()
    return {"items": [_serialize_automation_event(item) for item in rows]}


@router.get("/calendar", status_code=status.HTTP_200_OK)
def get_calendar(
    project_id: UUID = Query(...),
    from_dt: datetime = Query(..., alias="from"),
    to_dt: datetime = Query(..., alias="to"),
    db: Session = Depends(get_db),
    tenant_id: UUID = Depends(require_tenant_id),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    _ensure_project_access(db, tenant_id=tenant_id, project_id=project_id)
    from_value = from_dt if from_dt.tzinfo else from_dt.replace(tzinfo=UTC)
    to_value = to_dt if to_dt.tzinfo else to_dt.replace(tzinfo=UTC)
    if from_value > to_value:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="'from' must be before 'to'")

    posts = db.execute(
        select(Post).where(
            Post.company_id == tenant_id,
            Post.project_id == project_id,
            Post.publish_at.is_not(None),
            Post.publish_at >= from_value,
            Post.publish_at <= to_value,
        )
    ).scalars().all()
    content_items = db.execute(
        select(ContentItem).where(
            ContentItem.company_id == tenant_id,
            ContentItem.project_id == project_id,
            ContentItem.created_at >= from_value,
            ContentItem.created_at <= to_value,
        )
    ).scalars().all()

    return {
        "posts": [
            {
                "id": str(post.id),
                "project_id": str(post.project_id),
                "title": post.title,
                "status": post.status,
                "publish_at": post.publish_at.isoformat() if post.publish_at else None,
            }
            for post in posts
        ],
        "content_items": [
            {
                "id": str(item.id),
                "project_id": str(item.project_id),
                "title": item.title,
                "status": item.status,
                "created_at": item.created_at.isoformat(),
                "scheduled_for": (item.metadata_json or {}).get("scheduled_for"),
            }
            for item in content_items
        ],
    }
