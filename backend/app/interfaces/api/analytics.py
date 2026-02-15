from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.services.analytics_service import (
    get_activity_stream,
    get_publishing_summary,
    get_publishing_timeseries,
    parse_time_range_days,
)
from app.domain.models.user import User
from app.infrastructure.cache.redis_client import get_redis_client
from app.infrastructure.db.async_session import get_async_db
from app.interfaces.api.deps import get_current_user, require_tenant_id

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/publishing-summary", status_code=status.HTTP_200_OK)
async def publishing_summary(
    project_id: UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_async_db),
    tenant_id: UUID = Depends(require_tenant_id),
    _current_user: User = Depends(get_current_user),
) -> dict:
    redis_client = get_redis_client()
    return await get_publishing_summary(
        db,
        redis_client,
        company_id=tenant_id,
        project_id=project_id,
    )


@router.get("/publishing-timeseries", status_code=status.HTTP_200_OK)
async def publishing_timeseries(
    project_id: UUID | None = Query(default=None),
    range: str = Query(default="7d"),  # noqa: A002
    db: AsyncSession = Depends(get_async_db),
    tenant_id: UUID = Depends(require_tenant_id),
    _current_user: User = Depends(get_current_user),
) -> list[dict]:
    try:
        range_days = parse_time_range_days(range)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    redis_client = get_redis_client()
    return await get_publishing_timeseries(
        db,
        redis_client,
        company_id=tenant_id,
        range_days=range_days,
        project_id=project_id,
    )


@router.get("/activity-stream", status_code=status.HTTP_200_OK)
async def activity_stream(
    project_id: UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_async_db),
    tenant_id: UUID = Depends(require_tenant_id),
    _current_user: User = Depends(get_current_user),
) -> list[dict]:
    redis_client = get_redis_client()
    return await get_activity_stream(
        db,
        redis_client,
        company_id=tenant_id,
        project_id=project_id,
        limit=limit,
    )
