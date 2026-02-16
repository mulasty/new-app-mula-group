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


def test_connector_hardening_endpoints(client: TestClient):
    signup = client.post(
        "/signup",
        json={"company_name": "Connector Tenant", "owner_email": "owner@connector.test", "owner_password": "secret1234"},
    )
    assert signup.status_code == 201
    tenant_id = signup.json()["company"]["id"]

    login = client.post(
        "/auth/login",
        headers={"X-Tenant-ID": tenant_id},
        json={"email": "owner@connector.test", "password": "secret1234"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_id}

    _enable_flag(client, headers, "v1_connector_hardening")
    _enable_flag(client, headers, "v1_connector_sandbox_mode")

    project = client.post("/projects", headers=headers, json={"name": "Connector Project"})
    assert project.status_code == 201
    project_id = project.json()["id"]
    channel = client.post("/channels", headers=headers, json={"project_id": project_id, "type": "website"})
    assert channel.status_code in {200, 201}
    channel_id = channel.json()["id"]

    health = client.get(f"/connectors/{channel_id}/health", headers=headers)
    assert health.status_code == 200
    assert "score" in health.json()

    sandbox = client.post(
        f"/connectors/{channel_id}/test-publish",
        headers=headers,
        params={"scenario": "simulate_rate_limit"},
    )
    assert sandbox.status_code == 200

    disconnect = client.post(f"/connectors/{channel_id}/disconnect", headers=headers)
    assert disconnect.status_code == 200
    assert disconnect.json()["updated"] is True
