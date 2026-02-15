# Control Center - SaaS Bootstrap

Control Center is a multi-tenant SaaS starter repository with FastAPI, PostgreSQL, Redis, Celery, and a React dashboard.

## Stack

- Python 3.11
- FastAPI
- PostgreSQL
- SQLAlchemy 2.x
- Redis
- Celery
- Alembic
- React + TypeScript + Vite + Tailwind
- Docker + Docker Compose

## Quick Start (Full Stack)

1. Create environment files:

```bash
cp .env.example .env
cp dashboard/.env.example dashboard/.env
```

2. Start the system:

```bash
docker compose up --build
```

3. Open apps:

- Backend API: `http://localhost:8000`
- Dashboard: `http://localhost:3000`

## Dashboard Local Development

```bash
cd dashboard
npm install
npm run dev
```

Dashboard env (`dashboard/.env`):

```env
VITE_API_BASE_URL=/api
VITE_PROXY_TARGET=http://localhost:8000
```

## Auth, Signup and RBAC (Backend)

- `POST /signup` creates Company + Owner + trial subscription and returns tokens
- `POST /auth/login` uses `X-Tenant-ID` and returns access/refresh JWT
- `POST /auth/refresh` rotates access/refresh pair from refresh token
- `GET /auth/me` requires Bearer access token
- `POST /projects` requires role `Owner` or `Admin`

## Publishing Engine (Phase-4 Vertical Slice)

Tenant-scoped publishing endpoints require:
- `Authorization: Bearer <access_token>`
- `X-Tenant-ID: <company-uuid>`

Implemented endpoints:
- `POST /channels` (website only; create or return existing)
- `GET /channels?project_id=...`
- `POST /posts`
- `GET /posts?project_id=...&status=...`
- `PATCH /posts/{id}`
- `POST /posts/{id}/schedule`
- `POST /posts/{id}/publish-now`
- `GET /posts/{id}/timeline`
- `GET /website/publications?project_id=...`
- `GET /ready` (DB + Redis readiness)

Background services:
- `worker` runs publish tasks
- `beat` runs scheduler every 30 seconds and enqueues due posts

Start full stack (including beat):

```bash
docker compose up --build
```

Run end-to-end publish flow smoke script:

```bash
cd backend
python scripts/test_publish_flow.py
```

## Tenant Context

Set tenant for tenant-scoped endpoints:

```text
X-Tenant-ID: <company-uuid>
```

## Dev Seed

```bash
cd backend
python scripts/seed_dev_data.py
```

Default dev owner credentials:
- email: `owner@controlcenter.local`
- password: `devpassword123`

## Tests (integration)

Requires PostgreSQL reachable by `TEST_DATABASE_URL` (or `DATABASE_URL`):

```bash
cd backend
pip install -r requirements.txt -r requirements-dev.txt
pytest -q
```

## Automation (`Makefile` / `justfile`)

From repository root:

```bash
make install-dev
make seed
make test
make lint
make format
make dashboard-install
make dashboard-build
make dashboard-test
```

or:

```bash
just install-dev
just seed
just test
just lint
just format
just dashboard-install
just dashboard-build
just dashboard-test
```

## Testing

See `TESTING.md` for quick smoke scenarios and active test credentials.
