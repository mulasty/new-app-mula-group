from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.application.services.auth_service import AuthService
from app.core.security import create_access_token, create_refresh_token
from app.infrastructure.db.session import get_db

router = APIRouter(tags=["signup"])


class SignupRequest(BaseModel):
    company_name: str = Field(min_length=2, max_length=255)
    owner_email: str
    owner_password: str = Field(min_length=8)


@router.post("/signup", status_code=status.HTTP_201_CREATED)
def signup(payload: SignupRequest, db: Session = Depends(get_db)) -> dict:
    company, owner, subscription = AuthService.signup_tenant(
        db,
        company_name=payload.company_name,
        owner_email=payload.owner_email,
        owner_password=payload.owner_password,
    )

    access_token = create_access_token(user_id=owner.id, company_id=company.id)
    refresh_token = create_refresh_token(user_id=owner.id, company_id=company.id)

    return {
        "company": {
            "id": str(company.id),
            "name": company.name,
            "slug": company.slug,
        },
        "owner": {
            "id": str(owner.id),
            "email": owner.email,
            "role": owner.role,
        },
        "subscription": {
            "plan_code": subscription.plan_code,
            "status": subscription.status,
            "is_trial": subscription.is_trial,
        },
        "tokens": {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
        },
    }
