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


def _signup_and_login(client: TestClient) -> tuple[str, str]:
    signup_response = client.post(
        "/signup",
        json={
            "company_name": "Activation Tenant",
            "owner_email": "owner@activation.test",
            "owner_password": "secret1234",
        },
    )
    assert signup_response.status_code == 201
    company_id = signup_response.json()["company"]["id"]

    login_response = client.post(
        "/auth/login",
        headers={"X-Tenant-ID": company_id},
        json={"email": "owner@activation.test", "password": "secret1234"},
    )
    assert login_response.status_code == 200
    access_token = login_response.json()["access_token"]
    return company_id, access_token


def test_create_post_from_template_and_billing_history(client: TestClient):
    company_id, access_token = _signup_and_login(client)
    headers = {"Authorization": f"Bearer {access_token}", "X-Tenant-ID": company_id}

    project = client.post("/projects", headers=headers, json={"name": "Workspace"})
    assert project.status_code == 201
    project_id = project.json()["id"]

    template = client.post(
        "/templates",
        headers=headers,
        json={
            "project_id": project_id,
            "name": "Educational",
            "category": "educational",
            "tone": "professional",
            "content_structure": "Hook -> value -> CTA",
            "template_type": "post_text",
            "prompt_template": "Napisz post o {{topic}} dla {{project_name}}",
            "output_schema_json": {"type": "object"},
        },
    )
    assert template.status_code == 201
    template_id = template.json()["id"]

    post_from_template = client.post(
        "/posts/from-template",
        headers=headers,
        json={
            "project_id": project_id,
            "template_id": template_id,
            "variables": {"topic": "analytics"},
            "title": "Generated post",
            "status": "draft",
        },
    )
    assert post_from_template.status_code == 201
    assert post_from_template.json()["title"] == "Generated post"

    upgrade = client.post("/billing/upgrade", headers=headers, json={"plan_name": "Starter"})
    assert upgrade.status_code == 200

    cancel = client.post("/billing/cancel", headers=headers, json={"immediate": False})
    assert cancel.status_code == 200

    history = client.get("/billing/history", headers=headers)
    assert history.status_code == 200
    items = history.json()["items"]
    assert len(items) >= 2
