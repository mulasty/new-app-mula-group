from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models.project import Project
from app.domain.models.user import User, UserRole
from app.interfaces.api.deps import require_roles, require_tenant_id
from app.infrastructure.db.session import get_db

router = APIRouter(prefix="/projects", tags=["projects"])


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=255)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreateRequest,
    db: Session = Depends(get_db),
    tenant_id: UUID = Depends(require_tenant_id),
    current_user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN)),
) -> dict:
    project = Project(company_id=tenant_id, name=payload.name.strip())
    db.add(project)
    db.commit()
    db.refresh(project)

    return {
        "id": str(project.id),
        "company_id": str(project.company_id),
        "name": project.name,
    }


@router.get("", status_code=status.HTTP_200_OK)
def list_projects(
    db: Session = Depends(get_db),
    tenant_id: UUID = Depends(require_tenant_id),
    current_user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER, UserRole.EDITOR, UserRole.VIEWER)),
) -> dict:
    rows = db.execute(select(Project).where(Project.company_id == tenant_id).order_by(Project.created_at.desc())).scalars().all()
    return {
        "items": [
            {
                "id": str(project.id),
                "company_id": str(project.company_id),
                "name": project.name,
                "created_at": project.created_at.isoformat(),
            }
            for project in rows
        ]
    }
