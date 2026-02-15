import os
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from app.application.services import automation_service
from app.domain.models.automation_event import AutomationEvent
from app.domain.models.automation_rule import AutomationRule
from app.domain.models.automation_run import AutomationRun
from app.domain.models.content_item import ContentItem, ContentItemSource, ContentItemStatus
from app.infrastructure.db.base import Base
from app.infrastructure.db.session import get_db
from main import app

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", os.getenv("DATABASE_URL", ""))


@pytest.fixture(scope="session")
def db_engine():
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL or DATABASE_URL is required for integration tests")

    engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        pytest.skip(f"Database unavailable for integration tests: {exc}")

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session(db_engine):
    testing_session_local = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    session = testing_session_local()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _signup_and_login(client: TestClient, *, company_name: str, email: str, password: str = "secret123") -> tuple[str, str]:
    signup_response = client.post(
        "/signup",
        json={
            "company_name": company_name,
            "owner_email": email,
            "owner_password": password,
        },
    )
    assert signup_response.status_code == 201
    company_id = signup_response.json()["company"]["id"]

    login_response = client.post(
        "/auth/login",
        headers={"X-Tenant-ID": company_id},
        json={"email": email, "password": password},
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    return company_id, token


def _create_project(client: TestClient, *, company_id: str, token: str, name: str = "Automation Project") -> str:
    response = client.post(
        "/projects",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": company_id},
        json={"name": name},
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_automation_tenant_isolation_blocks_cross_tenant_campaign_create(client: TestClient):
    company_a, token_a = _signup_and_login(client, company_name="Tenant A", email="owner-a@test.local")
    company_b, token_b = _signup_and_login(client, company_name="Tenant B", email="owner-b@test.local")
    assert token_b

    project_a = _create_project(client, company_id=company_a, token=token_a, name="Project A")
    response = client.post(
        "/campaigns",
        headers={"Authorization": f"Bearer {token_a}", "X-Tenant-ID": company_b},
        json={
            "project_id": project_a,
            "name": "Cross tenant campaign",
            "timezone": "Europe/Warsaw",
            "language": "pl",
            "brand_profile_json": {},
        },
    )
    assert response.status_code == 403


def test_run_now_creates_run_and_queue_event(client: TestClient, db_session):
    company_id, token = _signup_and_login(client, company_name="RunNow Tenant", email="run-now@test.local")
    project_id = _create_project(client, company_id=company_id, token=token)

    rule_response = client.post(
        "/automation/rules",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": company_id},
        json={
            "project_id": project_id,
            "name": "Run now test",
            "trigger_type": "interval",
            "trigger_config_json": {"interval_seconds": 600},
            "action_type": "sync_metrics",
            "action_config_json": {},
            "guardrails_json": {},
        },
    )
    assert rule_response.status_code == 201
    rule_id = rule_response.json()["id"]

    run_response = client.post(
        f"/automation/rules/{rule_id}/run-now",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": company_id},
    )
    assert run_response.status_code == 202
    run_id = run_response.json()["run_id"]
    UUID(run_id)

    run_row = db_session.execute(
        select(AutomationRun).where(
            AutomationRun.id == UUID(run_id),
            AutomationRun.company_id == UUID(company_id),
        )
    ).scalar_one_or_none()
    assert run_row is not None

    queue_event = db_session.execute(
        select(AutomationEvent).where(
            AutomationEvent.run_id == UUID(run_id),
            AutomationEvent.company_id == UUID(company_id),
            AutomationEvent.event_type == "AutomationRunQueued",
        )
    ).scalar_one_or_none()
    assert queue_event is not None


def test_guardrails_duplicate_topic_forces_needs_review(db_session):
    from app.application.services.auth_service import AuthService
    from app.domain.models.project import Project

    company, _, _ = AuthService.signup_tenant(
        db_session,
        company_name="Guardrails Tenant",
        owner_email="guardrails@test.local",
        owner_password="secret123",
    )
    project = Project(company_id=company.id, name="Guardrails Project")
    db_session.add(project)
    db_session.flush()
    company_id = company.id
    project_id = project.id
    rule_id = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")
    run_id = UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd")

    existing = ContentItem(
        company_id=company_id,
        project_id=project_id,
        status=ContentItemStatus.DRAFT.value,
        title="Powtarzalny temat",
        body="Wcześniejszy wpis o tym samym temacie.",
        metadata_json={},
        source=ContentItemSource.MANUAL.value,
    )
    db_session.add(existing)
    db_session.flush()

    rule = AutomationRule(
        id=rule_id,
        company_id=company_id,
        project_id=project_id,
        name="Guardrail test",
        is_enabled=True,
        trigger_type="interval",
        trigger_config_json={"interval_seconds": 600},
        action_type="generate_post",
        action_config_json={"variables": {"topic": "test"}},
        guardrails_json={"duplicate_topic_days": 30, "approval_required": False},
    )
    db_session.add(rule)
    db_session.flush()

    run = AutomationRun(
        id=run_id,
        company_id=company_id,
        project_id=project_id,
        rule_id=rule_id,
        status="queued",
        stats_json={},
    )
    db_session.add(run)
    db_session.commit()

    class FakeProvider:
        async def generate_post_text(self, request):  # noqa: ANN001
            return {
                "title": "Powtarzalny temat",
                "body": "To jest wystarczająco długi tekst po polsku i zawiera słowo oraz oraz że się na potrzeby testu.",
                "hashtags": ["#test"],
                "cta": "Sprawdź demo",
                "channels": ["linkedin"],
                "risk_flags": ["none"],
            }

    automation_service.get_ai_provider = lambda: FakeProvider()  # type: ignore[assignment]
    result = automation_service.execute_automation_run_runtime(db_session, run_id=run_id)
    db_session.commit()
    assert result["status"] == "success"

    generated = db_session.execute(
        select(ContentItem).where(
            ContentItem.company_id == company_id,
            ContentItem.project_id == project_id,
            ContentItem.source == ContentItemSource.AI.value,
        )
    ).scalars().all()
    assert generated
    newest = generated[-1]
    assert newest.status == ContentItemStatus.NEEDS_REVIEW.value
    violations = (newest.metadata_json or {}).get("guardrail_violations", [])
    assert "duplicate_topic" in violations
