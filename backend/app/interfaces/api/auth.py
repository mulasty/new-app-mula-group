from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.application.services.auth_service import AuthService
from app.core.security import create_access_token, create_refresh_token, decode_token
from app.interfaces.api.deps import get_current_user, require_tenant_id
from app.infrastructure.db.session import get_db

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


@router.post("/login")
def login(
    payload: LoginRequest,
    db: Session = Depends(get_db),
    tenant_id=Depends(require_tenant_id),
) -> dict:
    user = AuthService.authenticate(db, company_id=tenant_id, email=payload.email, password=payload.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    access_token = create_access_token(user_id=user.id, company_id=user.company_id)
    refresh_token = create_refresh_token(user_id=user.id, company_id=user.company_id)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": {
            "id": str(user.id),
            "company_id": str(user.company_id),
            "email": user.email,
            "role": user.role,
        },
    }


@router.post("/refresh")
def refresh_tokens(payload: RefreshRequest, tenant_id=Depends(require_tenant_id)) -> dict:
    try:
        claims = decode_token(payload.refresh_token)
        company_id = UUID(claims["company_id"])
        user_id = UUID(claims["sub"])
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token") from exc

    if claims.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")

    if tenant_id != company_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant mismatch")

    return {
        "access_token": create_access_token(user_id=user_id, company_id=company_id),
        "refresh_token": create_refresh_token(user_id=user_id, company_id=company_id),
        "token_type": "bearer",
    }


@router.get("/me")
def me(current_user=Depends(get_current_user)) -> dict:
    return {
        "id": str(current_user.id),
        "company_id": str(current_user.company_id),
        "email": current_user.email,
        "role": current_user.role,
    }
