from uuid import UUID
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.application.services.auth_service import AuthService
from app.application.services.audit_service import log_audit_event
from app.application.services.token_security_service import (
    is_token_revoked,
    prune_expired_revoked_tokens,
    revoke_token,
)
from app.core.config import settings
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
    response: Response,
    db: Session = Depends(get_db),
    tenant_id=Depends(require_tenant_id),
) -> dict:
    user = AuthService.authenticate(db, company_id=tenant_id, email=payload.email, password=payload.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    access_token = create_access_token(user_id=user.id, company_id=user.company_id)
    refresh_token = create_refresh_token(user_id=user.id, company_id=user.company_id)
    log_audit_event(
        db,
        company_id=user.company_id,
        action="auth.login",
        metadata={"user_id": str(user.id), "email": user.email},
    )
    db.commit()

    if settings.auth_use_httponly_cookies:
        response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,
            secure=settings.auth_cookie_secure,
            samesite=settings.auth_cookie_samesite,
            domain=settings.auth_cookie_domain,
            max_age=settings.jwt_access_token_expire_minutes * 60,
            path="/",
        )

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": {
            "id": str(user.id),
            "company_id": str(user.company_id),
            "email": user.email,
            "role": user.role,
            "is_platform_admin": user.email.lower() in settings.platform_admin_email_list,
        },
    }


@router.post("/refresh")
def refresh_tokens(
    payload: RefreshRequest,
    response: Response,
    db: Session = Depends(get_db),
    tenant_id=Depends(require_tenant_id),
) -> dict:
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

    prune_expired_revoked_tokens(db)
    if is_token_revoked(db, token=payload.refresh_token, claims=claims):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token revoked")

    exp_raw = claims.get("exp")
    if not isinstance(exp_raw, (int, float)):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token payload")
    expires_at = datetime.fromtimestamp(exp_raw, tz=timezone.utc)
    revoke_token(
        db,
        token=payload.refresh_token,
        expires_at=expires_at,
        claims=claims,
    )
    db.commit()

    new_access_token = create_access_token(user_id=user_id, company_id=company_id)
    new_refresh_token = create_refresh_token(user_id=user_id, company_id=company_id)

    if settings.auth_use_httponly_cookies:
        response.set_cookie(
            key="access_token",
            value=new_access_token,
            httponly=True,
            secure=settings.auth_cookie_secure,
            samesite=settings.auth_cookie_samesite,
            domain=settings.auth_cookie_domain,
            max_age=settings.jwt_access_token_expire_minutes * 60,
            path="/",
        )

    return {
        "access_token": new_access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer",
    }


@router.get("/me")
def me(current_user=Depends(get_current_user)) -> dict:
    return {
        "id": str(current_user.id),
        "company_id": str(current_user.company_id),
        "email": current_user.email,
        "role": current_user.role,
        "is_platform_admin": current_user.email.lower() in settings.platform_admin_email_list,
    }
