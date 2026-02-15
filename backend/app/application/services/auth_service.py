import re
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.domain.models.company import Company
from app.domain.models.subscription import Subscription
from app.domain.models.user import User, UserRole


class AuthService:
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

    @staticmethod
    def signup_tenant(
        db: Session,
        *,
        company_name: str,
        owner_email: str,
        owner_password: str,
    ) -> tuple[Company, User, Subscription]:
        slug_base = re.sub(r"[^a-z0-9]+", "-", company_name.strip().lower()).strip("-") or "company"
        slug = slug_base
        counter = 1

        while db.execute(select(Company).where(Company.slug == slug)).scalar_one_or_none() is not None:
            counter += 1
            slug = f"{slug_base}-{counter}"

        try:
            company = Company(name=company_name.strip(), slug=slug, is_active=True)
            db.add(company)
            db.flush()

            owner = User(
                company_id=company.id,
                email=owner_email.strip().lower(),
                password_hash=hash_password(owner_password),
                role=UserRole.OWNER.value,
            )
            db.add(owner)

            subscription = Subscription(
                company_id=company.id,
                plan_code="trial",
                status="active",
                is_trial=True,
            )
            db.add(subscription)

            db.commit()
        except Exception:
            db.rollback()
            raise

        db.refresh(company)
        db.refresh(owner)
        db.refresh(subscription)
        return company, owner, subscription
