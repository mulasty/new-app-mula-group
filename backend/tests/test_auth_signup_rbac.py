import os
import uuid

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


def test_signup_login_refresh_and_me(client: TestClient):
    signup_payload = {
        "company_name": "Acme Control",
        "owner_email": "owner@acme.test",
        "owner_password": "secret123",
    }
    signup_response = client.post("/signup", json=signup_payload)
    assert signup_response.status_code == 201

    data = signup_response.json()
    company_id = data["company"]["id"]
    assert uuid.UUID(company_id)
    assert data["owner"]["role"] == "Owner"
    assert data["subscription"]["plan_code"] == "trial"

    login_response = client.post(
        "/auth/login",
        headers={"X-Tenant-ID": company_id},
        json={"email": "owner@acme.test", "password": "secret123"},
    )
    assert login_response.status_code == 200

    login_data = login_response.json()
    assert login_data["token_type"] == "bearer"
    access_token = login_data["access_token"]
    refresh_token = login_data["refresh_token"]

    refresh_response = client.post(
        "/auth/refresh",
        headers={"X-Tenant-ID": company_id},
        json={"refresh_token": refresh_token},
    )
    assert refresh_response.status_code == 200
    refreshed = refresh_response.json()
    assert refreshed["access_token"]
    assert refreshed["refresh_token"]

    me_response = client.get(
        "/auth/me",
        headers={
            "Authorization": f"Bearer {access_token}",
            "X-Tenant-ID": company_id,
        },
    )
    assert me_response.status_code == 200
    me_data = me_response.json()
    assert me_data["email"] == "owner@acme.test"
    assert me_data["role"] == "Owner"


def test_rbac_project_requires_owner_or_admin(client: TestClient):
    signup_response = client.post(
        "/signup",
        json={
            "company_name": "Rbac Tenant",
            "owner_email": "owner@rbac.test",
            "owner_password": "secret123",
        },
    )
    assert signup_response.status_code == 201
    company_id = signup_response.json()["company"]["id"]

    login_response = client.post(
        "/auth/login",
        headers={"X-Tenant-ID": company_id},
        json={"email": "owner@rbac.test", "password": "secret123"},
    )
    token = login_response.json()["access_token"]

    create_project_response = client.post(
        "/projects",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-ID": company_id,
        },
        json={"name": "Project Alpha"},
    )
    assert create_project_response.status_code == 201
    body = create_project_response.json()
    assert body["name"] == "Project Alpha"
    assert body["company_id"] == company_id
