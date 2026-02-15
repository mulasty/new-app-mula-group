from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models.user import User
from app.domain.models.website_publication import WebsitePublication
from app.interfaces.api.deps import get_current_user, require_tenant_id
from app.infrastructure.db.session import get_db

router = APIRouter(prefix="/website", tags=["website"])


@router.get("/publications", status_code=status.HTTP_200_OK)
def list_publications(
    project_id: UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    tenant_id: UUID = Depends(require_tenant_id),
    current_user: User = Depends(get_current_user),
) -> dict:
    query = select(WebsitePublication).where(WebsitePublication.company_id == tenant_id)
    if project_id is not None:
        query = query.where(WebsitePublication.project_id == project_id)

    rows = db.execute(query.order_by(WebsitePublication.published_at.desc())).scalars().all()
    return {
        "items": [
            {
                "id": str(row.id),
                "company_id": str(row.company_id),
                "project_id": str(row.project_id),
                "post_id": str(row.post_id),
                "slug": row.slug,
                "title": row.title,
                "content": row.content,
                "published_at": row.published_at.isoformat(),
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ]
    }
