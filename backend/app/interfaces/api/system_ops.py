from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.services.feature_flag_service import is_feature_enabled
from app.application.services.platform_ops_service import (
    TENANT_RISK_THRESHOLD,
    append_perf_sample,
    calculate_revenue_overview,
    calculate_system_health_score,
    calculate_tenant_risk_score,
    get_active_incidents,
    is_global_publish_paused,
    is_tenant_publish_paused,
    resolve_incident,
    set_global_publish_breaker,
    set_tenant_publish_breaker,
)
from app.domain.models.company import Company
from app.domain.models.feature_flag import FeatureFlag
from app.domain.models.platform_incident import PlatformIncident
from app.domain.models.tenant_risk_score import TenantRiskScore
from app.domain.models.user import User
from app.core.config import settings
from app.interfaces.api.deps import get_current_user, require_platform_admin, require_tenant_id
from app.infrastructure.db.session import get_db

router = APIRouter(tags=["system"])


class DashboardLoadPayload(BaseModel):
    load_time_ms: float = Field(gt=0, le=120000)


class EmergencyFlagOverrideRequest(BaseModel):
    key: str = Field(min_length=2, max_length=128)
    enabled_globally: bool


class GlobalBreakerRequest(BaseModel):
    enabled: bool
    reason: str = Field(default="manual_override", min_length=3, max_length=255)


class TenantBreakerRequest(BaseModel):
    enabled: bool
    reason: str = Field(default="manual_override", min_length=3, max_length=255)


class MaintenanceModeRequest(BaseModel):
    enabled: bool


@router.get("/system/health-score", status_code=status.HTTP_200_OK)
def get_system_health_score(
    db: Session = Depends(get_db),
    tenant_id: UUID = Depends(require_tenant_id),
    current_user: User = Depends(get_current_user),
) -> dict:
    health = calculate_system_health_score(db)
    db.commit()
    return {
        "score": health.score,
        "components": health.components,
        "alerts": {
            "publish_failure_rate_exceeded": health.publish_failure_rate > settings.system_publish_failure_alert_threshold,
            "db_latency_exceeded": health.db_latency_ms > settings.system_db_latency_alert_ms,
            "worker_backlog_exceeded": health.worker_backlog_size > settings.system_worker_backlog_alert_threshold,
        },
    }


@router.get("/tenants/{tenant_id}/risk-score", status_code=status.HTTP_200_OK)
def get_tenant_risk_score(
    tenant_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if tenant_id != current_user.company_id and current_user.email.lower() not in settings.platform_admin_email_list:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    company_exists = db.execute(select(Company.id).where(Company.id == tenant_id)).scalar_one_or_none()
    if company_exists is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    risk = calculate_tenant_risk_score(db, company_id=tenant_id)
    controls_enabled = is_feature_enabled(db, key="enforce_tenant_risk_controls", tenant_id=tenant_id)
    db.commit()
    return {
        **risk,
        "manual_approval_required": risk["risk_score"] >= TENANT_RISK_THRESHOLD,
        "controls_enabled": controls_enabled,
    }


@router.get("/metrics/revenue-overview", status_code=status.HTTP_200_OK)
def get_revenue_overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_admin),
) -> dict:
    overview = calculate_revenue_overview(db)
    db.commit()
    return overview


@router.post("/system/performance/dashboard-load", status_code=status.HTTP_202_ACCEPTED)
def track_dashboard_load(
    payload: DashboardLoadPayload,
    db: Session = Depends(get_db),
    tenant_id: UUID = Depends(require_tenant_id),
    current_user: User = Depends(get_current_user),
) -> dict:
    append_perf_sample("dashboard_load_time_ms", payload.load_time_ms)
    return {"accepted": True}


@router.get("/admin/system/overview", status_code=status.HTTP_200_OK)
def admin_system_overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_admin),
) -> dict:
    health = calculate_system_health_score(db)
    top_risk = db.execute(
        select(TenantRiskScore).order_by(TenantRiskScore.risk_score.desc()).limit(10)
    ).scalars().all()
    incidents = get_active_incidents(db, limit=100)
    revenue = calculate_revenue_overview(db)
    db.commit()
    return {
        "system_health_score": health.score,
        "components": health.components,
        "worker_queue_depth": health.worker_backlog_size,
        "tenant_risk_ranking": [
            {
                "company_id": str(item.company_id),
                "risk_score": item.risk_score,
                "risk_level": item.risk_level,
            }
            for item in top_risk
        ],
        "revenue": revenue["summary"],
        "active_incidents": incidents,
    }


@router.get("/admin/incidents", status_code=status.HTTP_200_OK)
def admin_incidents(
    status_filter: str = Query(default="open", alias="status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_admin),
) -> dict:
    query = select(PlatformIncident).order_by(PlatformIncident.created_at.desc())
    if status_filter:
        query = query.where(PlatformIncident.status == status_filter)
    rows = db.execute(query.limit(200)).scalars().all()
    return {
        "items": [
            {
                "id": str(item.id),
                "company_id": str(item.company_id) if item.company_id else None,
                "incident_type": item.incident_type,
                "severity": item.severity,
                "status": item.status,
                "message": item.message,
                "metadata_json": item.metadata_json or {},
                "created_at": item.created_at.isoformat(),
                "resolved_at": item.resolved_at.isoformat() if item.resolved_at else None,
            }
            for item in rows
        ]
    }


@router.post("/admin/incidents/{incident_id}/resolve", status_code=status.HTTP_200_OK)
def admin_resolve_incident(
    incident_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_admin),
) -> dict:
    incident = resolve_incident(db, incident_id=incident_id, resolved_by=current_user.email)
    if incident is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")
    db.commit()
    return {"id": str(incident.id), "status": incident.status}


@router.post("/admin/feature-flags/override", status_code=status.HTTP_200_OK)
def admin_feature_flag_override(
    payload: EmergencyFlagOverrideRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_admin),
) -> dict:
    flag = db.execute(select(FeatureFlag).where(FeatureFlag.key == payload.key)).scalar_one_or_none()
    if flag is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feature flag not found")
    flag.enabled_globally = payload.enabled_globally
    db.add(flag)
    db.commit()
    return {"key": flag.key, "enabled_globally": flag.enabled_globally}


@router.post("/admin/system/global-publish-breaker", status_code=status.HTTP_200_OK)
def admin_global_publish_breaker(
    payload: GlobalBreakerRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_admin),
) -> dict:
    set_global_publish_breaker(payload.enabled, reason=payload.reason)
    paused, reason = is_global_publish_paused()
    return {"enabled": paused, "reason": reason}


@router.post("/admin/system/tenants/{tenant_id}/publish-breaker", status_code=status.HTTP_200_OK)
def admin_tenant_publish_breaker(
    tenant_id: UUID,
    payload: TenantBreakerRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_admin),
) -> dict:
    set_tenant_publish_breaker(tenant_id, payload.enabled, reason=payload.reason)
    paused, reason = is_tenant_publish_paused(tenant_id)
    return {"tenant_id": str(tenant_id), "enabled": paused, "reason": reason}


@router.post("/admin/system/maintenance-mode", status_code=status.HTTP_200_OK)
def admin_maintenance_mode(
    payload: MaintenanceModeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_admin),
) -> dict:
    flag = db.execute(select(FeatureFlag).where(FeatureFlag.key == "maintenance_read_only_mode")).scalar_one_or_none()
    if flag is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feature flag not found")
    flag.enabled_globally = payload.enabled
    db.add(flag)
    db.commit()
    return {"enabled": flag.enabled_globally}
