from sqlalchemy import select

from app.application.services.auth_service import AuthService
from app.domain.models.company import Company
from app.domain.models.subscription import Subscription
from app.domain.models.user import User
from app.infrastructure.db.session import SessionLocal


DEFAULT_COMPANY_NAME = "Control Center Dev"
DEFAULT_OWNER_EMAIL = "owner@controlcenter.local"
DEFAULT_OWNER_PASSWORD = "devpassword123"


def seed_dev_data() -> None:
    with SessionLocal() as db:
        existing_company = db.execute(select(Company).where(Company.slug == "control-center-dev")).scalar_one_or_none()
        if existing_company is not None:
            print(f"Seed exists: company_id={existing_company.id}")
            return

        company, owner, subscription = AuthService.signup_tenant(
            db,
            company_name=DEFAULT_COMPANY_NAME,
            owner_email=DEFAULT_OWNER_EMAIL,
            owner_password=DEFAULT_OWNER_PASSWORD,
        )

        print("Created dev seed data:")
        print(f"- company_id: {company.id}")
        print(f"- owner_id: {owner.id}")
        print(f"- owner_email: {owner.email}")
        print(f"- subscription_plan: {subscription.plan_code}")


if __name__ == "__main__":
    seed_dev_data()
