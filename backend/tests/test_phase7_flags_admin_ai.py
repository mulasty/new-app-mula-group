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


def _signup(client: TestClient, company_name: str, email: str, password: str = "secret123") -> tuple[str, str]:
    signup_response = client.post(
        "/signup",
        json={"company_name": company_name, "owner_email": email, "owner_password": password},
    )
    assert signup_response.status_code == 201
    company_id = signup_response.json()["company"]["id"]
    login_response = client.post(
        "/auth/login",
        headers={"X-Tenant-ID": company_id},
        json={"email": email, "password": password},
    )
    assert login_response.status_code == 200
    return company_id, login_response.json()["access_token"]


def test_feature_flags_and_ai_quality_flow(client: TestClient):
    tenant_id, token = _signup(client, "Flags Tenant", "flags-owner@test.local")
    headers = {"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_id}

    flags_response = client.get("/feature-flags", headers=headers)
    assert flags_response.status_code == 200
    items = flags_response.json()["items"]
    assert len(items) >= 3
    ai_flag = next(item for item in items if item["key"] == "beta_ai_quality")

    project_response = client.post("/projects", headers=headers, json={"name": "AI Project"})
    assert project_response.status_code == 201
    project_id = project_response.json()["id"]

    evaluate_response_disabled = client.post(
        "/ai-quality/evaluate",
        headers=headers,
        json={"project_id": project_id, "title": "test", "body": "simple body"},
    )
    assert evaluate_response_disabled.status_code == 404

    patch_response = client.patch(
        f"/feature-flags/{ai_flag['id']}",
        headers=headers,
        json={"enabled_for_tenant": True},
    )
    assert patch_response.status_code == 200

    evaluate_response = client.post(
        "/ai-quality/evaluate",
        headers=headers,
        json={"project_id": project_id, "title": "TEST", "body": "BUY NOW!!!! #promo #promo #promo"},
    )
    assert evaluate_response.status_code == 200
    assert "risk_score" in evaluate_response.json()


def test_admin_endpoints_require_platform_admin_and_flag(client: TestClient):
    tenant_id, token = _signup(client, "Admin Tenant", "platform-admin@test.local")
    headers = {"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_id}

    denied_response = client.get("/admin/tenants", headers=headers)
    assert denied_response.status_code in {403, 404}

    flags_response = client.get("/feature-flags", headers=headers)
    assert flags_response.status_code == 200
    admin_flag = next(item for item in flags_response.json()["items"] if item["key"] == "beta_admin_panel")

    patch_response = client.patch(
        f"/feature-flags/{admin_flag['id']}",
        headers=headers,
        json={"enabled_globally": True},
    )
    assert patch_response.status_code == 200

    previous_admin_emails = settings.platform_admin_emails
    try:
        settings.platform_admin_emails = "platform-admin@test.local"
        access_response = client.get("/admin/tenants", headers=headers)
        assert access_response.status_code == 200
        assert isinstance(access_response.json()["items"], list)
    finally:
        settings.platform_admin_emails = previous_admin_emails
