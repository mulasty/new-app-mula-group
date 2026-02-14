from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.domain.models.user import User


class AuthService:
    @staticmethod
    def register_user(db: Session, *, company_id: UUID, email: str, password: str, full_name: str | None) -> User:
        normalized_email = email.strip().lower()
        existing = db.execute(
            select(User).where(User.company_id == company_id, User.email == normalized_email)
        ).scalar_one_or_none()
        if existing:
            raise ValueError("User with this email already exists for tenant")

        user = User(
            company_id=company_id,
            email=normalized_email,
            password_hash=hash_password(password),
            full_name=full_name,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def authenticate(db: Session, *, company_id: UUID, email: str, password: str) -> User | None:
        normalized_email = email.strip().lower()
        user = db.execute(
            select(User).where(User.company_id == company_id, User.email == normalized_email)
        ).scalar_one_or_none()
        if not user:
            return None
        if not verify_password(password, user.password_hash):
            return None
        return user
