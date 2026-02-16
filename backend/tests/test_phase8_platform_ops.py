import os
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
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
        json={"company_name": company_name, "owner_email": email, "owner_password": password},
    )
    assert signup_response.status_code == 201
    tenant_id = signup_response.json()["company"]["id"]
    login_response = client.post(
        "/auth/login",
        headers={"X-Tenant-ID": tenant_id},
        json={"email": email, "password": password},
    )
    assert login_response.status_code == 200
    return tenant_id, login_response.json()["access_token"]


def test_system_health_and_risk_score_endpoints(client: TestClient):
    tenant_id, token = _signup_and_login(client, company_name="Ops Tenant", email="ops@test.local")
    headers = {"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_id}

    health_response = client.get("/system/health-score", headers=headers)
    assert health_response.status_code == 200
    assert "score" in health_response.json()

    risk_response = client.get(f"/tenants/{tenant_id}/risk-score", headers=headers)
    assert risk_response.status_code == 200
    assert "risk_score" in risk_response.json()


def test_admin_overview_and_global_breaker(client: TestClient):
    tenant_id, token = _signup_and_login(client, company_name="Ops Admin Tenant", email="ops-admin@test.local")
    headers = {"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_id}

    flags_response = client.get("/feature-flags", headers=headers)
    assert flags_response.status_code == 200
    flags = flags_response.json()["items"]
    beta_admin_flag = next(item for item in flags if item["key"] == "beta_admin_panel")
    patch_response = client.patch(
        f"/feature-flags/{beta_admin_flag['id']}",
        headers=headers,
        json={"enabled_globally": True},
    )
    assert patch_response.status_code == 200

    previous_admin_emails = settings.platform_admin_emails
    settings.platform_admin_emails = "ops-admin@test.local"
    try:
        overview = client.get("/admin/system/overview", headers=headers)
        assert overview.status_code == 200
        assert "system_health_score" in overview.json()

        project = client.post("/projects", headers=headers, json={"name": "Breaker Project"})
        assert project.status_code == 201
        project_id = project.json()["id"]
        create_post = client.post(
            "/posts",
            headers=headers,
            json={"project_id": project_id, "title": "Breaker Post", "content": "Body"},
        )
        assert create_post.status_code == 201
        post_id = create_post.json()["id"]

        enable_breaker = client.post(
            "/admin/system/global-publish-breaker",
            headers=headers,
            json={"enabled": True, "reason": "test"},
        )
        assert enable_breaker.status_code == 200

        publish_now = client.post(f"/posts/{post_id}/publish-now", headers=headers)
        assert publish_now.status_code == 503

        disable_breaker = client.post(
            "/admin/system/global-publish-breaker",
            headers=headers,
            json={"enabled": False, "reason": "rollback"},
        )
        assert disable_breaker.status_code == 200
    finally:
        settings.platform_admin_emails = previous_admin_emails
