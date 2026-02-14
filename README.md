# Control Center - SaaS Bootstrap

Control Center is a multi-tenant SaaS starter repository with FastAPI, PostgreSQL, Redis, Celery, and Alembic migrations.

## Stack

- Python 3.11
- FastAPI
- PostgreSQL
- SQLAlchemy 2.x
- Redis
- Celery
- Alembic
- Docker + Docker Compose

## Quick Start

1. Create environment file:

```bash
cp .env.example .env
```

2. Start the system:

```bash
docker compose up --build
```

3. Verify endpoints:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/tenant/context
```

The backend container runs `alembic upgrade head` before API startup.

## Auth Skeleton

- `POST /auth/register` (requires `X-Tenant-ID` header)
- `POST /auth/login` (requires `X-Tenant-ID` header)
- `GET /auth/me` (requires Bearer token)

## Tenant Context

Set the tenant on each request with header:

```text
X-Tenant-ID: <company-uuid>
```

## Local Backend Development (optional)

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
alembic upgrade head
uvicorn main:app --reload
```
