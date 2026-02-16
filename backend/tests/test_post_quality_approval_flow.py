import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

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


def _enable_flag(client: TestClient, headers: dict, key: str) -> None:
    flags = client.get("/feature-flags", headers=headers)
    assert flags.status_code == 200
    item = next((row for row in flags.json().get("items", []) if row["key"] == key), None)
    assert item is not None
    update = client.patch(f"/feature-flags/{item['id']}", headers=headers, json={"enabled_for_tenant": True})
    assert update.status_code == 200


def test_quality_gate_approval_flow(client: TestClient):
    signup = client.post(
        "/signup",
        json={"company_name": "AIQ Tenant", "owner_email": "owner@aiq.test", "owner_password": "secret1234"},
    )
    assert signup.status_code == 201
    tenant_id = signup.json()["company"]["id"]

    login = client.post(
        "/auth/login",
        headers={"X-Tenant-ID": tenant_id},
        json={"email": "owner@aiq.test", "password": "secret1234"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_id}

    _enable_flag(client, headers, "v1_ai_quality_engine")
    _enable_flag(client, headers, "v1_ai_quality_gate")

    project = client.post("/projects", headers=headers, json={"name": "AIQ Project"})
    assert project.status_code == 201
    project_id = project.json()["id"]

    profile = client.post(
        "/brand-profiles",
        headers=headers,
        json={
            "project_id": project_id,
            "brand_name": "Control Center",
            "language": "pl",
            "tone": "professional",
            "do_list": [],
            "dont_list": ["cheap"],
            "forbidden_claims": ["guaranteed roi"],
            "preferred_hashtags": [],
        },
    )
    assert profile.status_code == 201

    post = client.post(
        "/posts",
        headers=headers,
        json={
            "project_id": project_id,
            "title": "GUARANTEED ROI!!!",
            "content": "Contact us at sales@example.com for guaranteed ROI now!!!!",
        },
    )
    assert post.status_code == 201
    post_id = post.json()["id"]

    quality = client.post(f"/posts/{post_id}/quality-check", headers=headers, json={})
    assert quality.status_code == 200
    assert quality.json()["risk_level"] == "high"
    assert quality.json()["status"] == "needs_approval"

    blocked = client.post(f"/posts/{post_id}/publish-now", headers=headers)
    assert blocked.status_code == 409

    approve = client.post(f"/posts/{post_id}/approve", headers=headers)
    assert approve.status_code == 200
    assert approve.json()["status"] == "draft"

    reject = client.post(f"/posts/{post_id}/reject", headers=headers, json={"reason": "manual review required"})
    assert reject.status_code == 200
    assert reject.json()["status"] == "needs_approval"
