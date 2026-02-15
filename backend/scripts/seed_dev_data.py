from sqlalchemy import select

from app.application.services.auth_service import AuthService
from app.domain.models.automation_rule import AutomationRule
from app.domain.models.campaign import Campaign, CampaignStatus
from app.domain.models.company import Company
from app.domain.models.content_template import ContentTemplate, ContentTemplateType
from app.domain.models.project import Project
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

        project = Project(company_id=company.id, name="Control Center Lab")
        db.add(project)
        db.flush()

        campaign = Campaign(
            company_id=company.id,
            project_id=project.id,
            name="Launch Automation",
            description="Seed campaign for Phase 6 testing",
            status=CampaignStatus.ACTIVE.value,
            timezone="Europe/Warsaw",
            language="pl",
            brand_profile_json={
                "voice": "professional",
                "forbidden_topics": ["medical claims"],
                "forbidden_words": ["guaranteed profit"],
            },
        )
        db.add(campaign)
        db.flush()

        template = ContentTemplate(
            company_id=company.id,
            project_id=project.id,
            name="Post Text PL",
            template_type=ContentTemplateType.POST_TEXT.value,
            prompt_template="Napisz post o {{topic}} dla marki o glosie {{brand.voice}} z CTA {{offer}}.",
            output_schema_json={
                "type": "object",
                "required": ["title", "body", "hashtags", "cta", "channels", "risk_flags"],
            },
            default_values_json={"topic": "nowa funkcja", "offer": "umow demo"},
        )
        db.add(template)
        db.flush()

        rule = AutomationRule(
            company_id=company.id,
            project_id=project.id,
            campaign_id=campaign.id,
            name="Daily generate post",
            is_enabled=True,
            trigger_type="interval",
            trigger_config_json={"interval_seconds": 3600},
            action_type="generate_post",
            action_config_json={"template_id": str(template.id), "variables": {"topic": "publishing automation"}},
            guardrails_json={"approval_required": True, "max_posts_per_day_project": 3, "duplicate_topic_days": 7},
        )
        db.add(rule)

        db.commit()

        print("Created dev seed data:")
        print(f"- company_id: {company.id}")
        print(f"- owner_id: {owner.id}")
        print(f"- owner_email: {owner.email}")
        print(f"- subscription_plan: {subscription.plan_code}")
        print(f"- project_id: {project.id}")
        print(f"- campaign_id: {campaign.id}")
        print(f"- template_id: {template.id}")
        print(f"- automation_rule_id: {rule.id}")


if __name__ == "__main__":
    seed_dev_data()
