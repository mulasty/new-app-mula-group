from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.application.services.auth_service import AuthService
from app.core.security import create_access_token
from app.interfaces.api.deps import get_current_user_claims, require_tenant_id
from app.infrastructure.db.session import get_db

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: str
    password: str = Field(min_length=8)
    full_name: str | None = None


class LoginRequest(BaseModel):
    email: str
    password: str


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterRequest,
    db: Session = Depends(get_db),
    tenant_id: UUID = Depends(require_tenant_id),
) -> dict:
    try:
        user = AuthService.register_user(
            db,
            company_id=tenant_id,
            email=payload.email,
            password=payload.password,
            full_name=payload.full_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return {
        "id": str(user.id),
        "company_id": str(user.company_id),
        "email": user.email,
        "full_name": user.full_name,
    }


@router.post("/login")
def login(
    payload: LoginRequest,
    db: Session = Depends(get_db),
    tenant_id: UUID = Depends(require_tenant_id),
) -> dict:
    user = AuthService.authenticate(db, company_id=tenant_id, email=payload.email, password=payload.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    token = create_access_token(user_id=user.id, company_id=user.company_id)
    return {"access_token": token, "token_type": "bearer"}


@router.get("/me")
def me(claims: dict = Depends(get_current_user_claims)) -> dict:
    return {
        "user_id": claims.get("sub"),
        "company_id": claims.get("company_id"),
        "token_type": claims.get("type"),
    }
