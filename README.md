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

## Analytics (Phase-4.2)

Tenant-scoped analytics endpoints:
- `GET /analytics/publishing-summary?project_id=...`
- `GET /analytics/publishing-timeseries?project_id=...&range=7d|30d|90d`
- `GET /analytics/activity-stream?project_id=...&limit=50`

Implementation details:
- strict tenant isolation (`Authorization` + `X-Tenant-ID`)
- async SQLAlchemy session for analytics queries
- Redis cache with short TTL (45s)
- indexes optimized for analytics reads on `publish_events`

## Campaign Automation Engine (Phase-6)

Phase 6 introduces tenant-safe campaign automation runtime with scheduling, event triggers, AI generation, approvals, and execution tracking.

New backend domains:
- `campaigns`
- `automation_rules`
- `content_templates`
- `content_items`
- `approvals`
- `automation_runs`
- `automation_events`

New endpoints (tenant-scoped, require `Authorization` + `X-Tenant-ID`):
- Campaigns:
  - `POST /campaigns`
  - `GET /campaigns?project_id=...`
  - `PATCH /campaigns/{id}`
  - `POST /campaigns/{id}/activate`
  - `POST /campaigns/{id}/pause`
- Templates:
  - `POST /templates`
  - `GET /templates?project_id=...`
  - `PATCH /templates/{id}`
- Automation rules:
  - `POST /automation/rules`
  - `GET /automation/rules?project_id=...&campaign_id=...`
  - `PATCH /automation/rules/{id}`
  - `POST /automation/rules/{id}/run-now`
- Content studio:
  - `GET /content?project_id=...&status=...`
  - `POST /content`
  - `POST /content/{id}/approve`
  - `POST /content/{id}/reject`
  - `POST /content/{id}/schedule`
- Monitoring:
  - `GET /automation/runs?project_id=...&rule_id=...`
  - `GET /automation/runs/{id}/events`
- Calendar:
  - `GET /calendar?project_id=...&from=...&to=...`

Automation runtime:
- Celery Beat schedules:
  - `workers.tasks.schedule_due_automation_rules` (every 30s)
  - `workers.tasks.process_publish_event_rules` (every 20s)
- Worker task:
  - `workers.tasks.execute_automation_run`

AI provider configuration (OpenAI):
- `AI_PROVIDER=openai`
- `OPENAI_API_KEY=...`
- `OPENAI_MODEL=gpt-4o-mini`
- `OPENAI_BASE_URL=https://api.openai.com/v1`
- `OPENAI_TIMEOUT_SECONDS=30`
- `OPENAI_TEMPERATURE=0.2`

Guardrails currently enforced in runtime:
- max posts/day per project
- quiet hours
- blackout dates
- duplicate topic detection (`duplicate_topic_days`)
- approval-required escalation

Dashboard additions:
- `/app/campaigns`
- `/app/automations`
- `/app/content-studio`
- `/app/calendar`

Manual test checklist:
1. Create project, campaign, and template.
2. Create automation rule and trigger `run-now`.
3. Verify `automation_runs` + `automation_events`.
4. Review content in Content Studio (`approve` / `reject` / `schedule`).
5. Verify scheduled items in Calendar.

## LinkedIn Connector (Phase-5.1)

LinkedIn connector extends the channel adapter architecture and publishes asynchronously via Celery worker.

Backend additions:
- OAuth start: `GET /channels/linkedin/oauth/start`
- OAuth callback: `GET /channels/linkedin/oauth/callback`
- New tenant-scoped table: `linkedin_accounts`
- Adapter dispatch in worker (`website`, `linkedin`) via channel adapter factory

Environment variables:
- `TOKEN_ENCRYPTION_KEY` (optional; falls back to `JWT_SECRET_KEY` derivation)
- `LINKEDIN_CLIENT_ID`
- `LINKEDIN_CLIENT_SECRET`
- `LINKEDIN_REDIRECT_URI`
- `LINKEDIN_DASHBOARD_REDIRECT_URL`
- `LINKEDIN_OAUTH_SCOPE`

Flow:
1. Connect LinkedIn from Dashboard Channels page.
2. OAuth callback stores encrypted LinkedIn tokens for tenant.
3. Worker resolves channel adapters and publishes posts to active channels.

## Meta Connector (Phase-5.3)

Meta connector adds Facebook Pages and Instagram Business integration using the same adapter-driven worker flow.

Backend additions:
- OAuth start: `GET /channels/meta/oauth/start`
- OAuth callback: `GET /channels/meta/oauth/callback`
- Meta connection snapshot: `GET /channels/meta/connections`
- New tables:
  - `facebook_accounts`
  - `facebook_pages`
  - `instagram_accounts`
- New adapters:
  - `facebook_adapter.py`
  - `instagram_adapter.py`

Meta OAuth scopes:
- `pages_manage_posts`
- `pages_read_engagement`
- `instagram_basic`
- `instagram_content_publish`

Environment variables:
- `META_APP_ID`
- `META_APP_SECRET`
- `META_REDIRECT_URI`
- `META_DASHBOARD_REDIRECT_URL`
- `META_OAUTH_SCOPE`
- `META_GRAPH_API_BASE_URL`

Worker metadata includes per-channel observability details:
- `external_post_id`
- `publish_latency_ms`
- `adapter_type`
- success/failure flags

## Universal Connector Framework (Phase-5.4)

Connector framework now supports adding new platforms without worker rewrites.

Backend additions:
- universal account store: `social_accounts`
- platform throttling config: `platform_rate_limits`
- dynamic connector catalog: `GET /connectors/available`
- standardized adapter contract:
  - `validate_credentials()`
  - `publish_text()`
  - `publish_media()`
  - `refresh_credentials()`
  - `get_capabilities()`
- shared media abstraction:
  - `app/integrations/media_upload_service.py`

Publish event metadata now includes:
- `adapter_type`
- `platform`
- `publish_duration_ms`
- `publish_latency_ms`
- `retry_count`

## Multi-Platform Connectors (Phase-5.5)

Phase-5.5 adds production-oriented connector flows for:
- TikTok (`type=tiktok`)
- Threads (`type=threads`)
- X / Twitter (`type=x`)
- Pinterest (`type=pinterest`)

Backend OAuth endpoints:
- `GET /channels/tiktok/oauth/start`
- `GET /channels/tiktok/oauth/callback`
- `GET /channels/threads/oauth/start`
- `GET /channels/threads/oauth/callback`
- `GET /channels/x/oauth/start`
- `GET /channels/x/oauth/callback`
- `GET /channels/pinterest/oauth/start`
- `GET /channels/pinterest/oauth/callback`

Connector catalog:
- `GET /connectors/available`

Schema/migrations:
- `social_accounts` (universal account/token store; encrypted tokens)
- `channel_publications` (idempotency mapping `post_id + channel_id -> external_post_id`)
- index: `social_accounts(company_id, platform)`
- index: `publish_events(company_id, project_id, created_at)`

Publishing behavior:
- adapters resolve dynamically by channel type
- worker publishes asynchronously only (no direct publish in API routes)
- per-channel telemetry is written to `publish_events.metadata_json`:
  - `external_post_id`
  - `publish_duration_ms`
  - `publish_latency_ms`
  - `adapter_type`
  - `platform`
  - retry/auth failure metadata
- auth failures disable the channel and emit `ChannelAuthFailed`

### Required Environment Variables (Phase-5.5)

Common:
- `PUBLIC_APP_URL` (dashboard base URL for OAuth redirect back)
- `API_BASE_URL` (backend base URL)
- `TOKEN_ENCRYPTION_KEY` (recommended, used for token encryption)

TikTok:
- `TIKTOK_CLIENT_KEY`
- `TIKTOK_CLIENT_SECRET`
- `TIKTOK_REDIRECT_URI`
- `TIKTOK_OAUTH_SCOPE`

Threads:
- `THREADS_APP_ID`
- `THREADS_APP_SECRET`
- `THREADS_REDIRECT_URI`
- `THREADS_OAUTH_SCOPE`

X:
- `X_CLIENT_ID`
- `X_CLIENT_SECRET`
- `X_REDIRECT_URI`
- `X_OAUTH_SCOPE`

Pinterest:
- `PINTEREST_CLIENT_ID`
- `PINTEREST_CLIENT_SECRET`
- `PINTEREST_REDIRECT_URI`
- `PINTEREST_OAUTH_SCOPE`

### Redirect URI Setup

Configure platform apps to use callback URLs matching `.env`:
- TikTok: `http://localhost:8000/channels/tiktok/oauth/callback`
- Threads: `http://localhost:8000/channels/threads/oauth/callback`
- X: `http://localhost:8000/channels/x/oauth/callback`
- Pinterest: `http://localhost:8000/channels/pinterest/oauth/callback`

### Smoke Scripts

Connector smoke (manual OAuth step included):

```bash
cd backend
bash scripts/test_connectors_smoke.sh
```

Multichannel publish smoke:

```bash
cd backend
bash scripts/test_publish_multichannel.sh
```

### Platform Notes / Limitations

- TikTok Content Posting may require app audit for full public publishing behavior; unaudited apps can be restricted to inbox/private flows depending on app state.
- Threads and X require app scopes/permissions aligned with write operations.
- Pinterest publishing requires board context and media URL for pin creation.
- Connectors never return access tokens to frontend; tokens are stored encrypted server-side.

### Official API References

- TikTok Content Posting API: https://developers.tiktok.com/doc/content-posting-api-reference-direct-post
- X create post endpoint (`POST /2/tweets`): https://docs.x.com/x-api/posts/creation-of-a-post
- Threads API docs: https://developers.facebook.com/docs/threads
- Pinterest API docs: https://developers.pinterest.com/docs/api/v5

## Connector Framework Hardening (Phase-5.2)

Publishing engine now supports scalable multi-connector behavior without changing core worker logic per channel:

- `channels.capabilities_json` stores adapter capabilities (`text`, `image`, `video`, `max_length`)
- adapter registry uses module discovery and auto-registration
- worker publishes to project channels concurrently and records per-channel latency metadata
- partial publish status supported: `published_partial`
- dynamic retry policies in `channel_retry_policies`:
  - `channel_type`
  - `max_attempts`
  - `backoff_strategy` (`linear` / `exponential`)
  - `retry_delay_seconds`

Per-channel publish metrics are written to `publish_events.metadata_json`:

- `publish_duration_ms`
- `adapter_type`
- `channel_type`
- `success`
- `retryable`

## Phase 6 Wave 1 - Infrastructure Hardening

Wave 1 adds additive infrastructure hardening without changing existing business endpoints:

- JSON structured logs for app + uvicorn (`timestamp`, `level`, `message`, `request_id`, `tenant_id`)
- request correlation middleware with `X-Request-ID`
- global error envelope:
  - `error_code`
  - `message`
  - `trace_id`
- tenant rate limiting in Redis (sliding window, default `120 req/min`)
- publish dead-letter persistence (`failed_jobs`) after retry exhaustion
- refresh-token revocation list + rotation hardening (`revoked_tokens`)
- security headers middleware + strict CORS origin configuration

### New Environment Variables (Wave 1)

- `FRONTEND_ORIGIN` (default `http://localhost:3000`)
- `ADDITIONAL_FRONTEND_ORIGINS` (comma-separated)
- `TENANT_RATE_LIMIT_PER_MINUTE` (default `120`)

### Smoke Checklist (Wave 1)

1. Start stack:
   - `docker compose up --build`
2. Check health and headers:
   - `GET /health` should return:
     - `X-Request-ID`
     - `X-Frame-Options: DENY`
     - `X-Content-Type-Options: nosniff`
3. Check error envelope:
   - call an invalid endpoint/body and verify:
     - `{ "error_code": "...", "message": "...", "trace_id": "..." }`
4. Check token rotation:
   - login -> refresh once -> reuse old refresh token should return `401`
5. Check tenant rate limit:
   - burst > `TENANT_RATE_LIMIT_PER_MINUTE` tenant-scoped requests within 1 minute
   - verify `429` with `error_code=rate_limit_exceeded`
6. Check dead-letter:
   - force publish task failure beyond retries and verify row in `failed_jobs`

## Phase 6 Wave 2 - Scaling and Observability

Wave 2 extends infrastructure operability without breaking existing API contracts:

- Prometheus metrics endpoint: `GET /metrics`
- Request metrics middleware:
  - `total_requests`
  - `request_latency_seconds`
- DB/Redis latency metrics:
  - `db_query_duration_seconds`
  - `redis_latency_seconds`
- Worker + scheduler metrics:
  - `publish_attempts_total`
  - `publish_failures_total`
  - `scheduled_jobs_checked_total`
- Enhanced health payload with latency and worker heartbeat:
  - `GET /health`
  - `GET /ready`
- Celery queue isolation:
  - `publishing`
  - `scheduler`
  - `analytics`
- Redis distributed lock for publish idempotency:
  - key: `lock:publish:{post_id}`
  - ttl: `60s`
- Scheduler query indexes for due-post scans.

New migration:
- `0011_wave2_scaling_observability`

New env vars used:
- `WORKER_HEARTBEAT_KEY` (default `worker:heartbeat`)
- `WORKER_HEARTBEAT_TTL_SECONDS` (default `45`)

## Phase 6 Wave 3 - Enterprise and Billing

Wave 3 adds production launch foundations with billing, quota enforcement, audit logs, and production deployment assets.

Backend additions:
- Billing tables:
  - `subscription_plans`
  - `company_subscriptions`
  - `company_usages`
- Audit table:
  - `audit_logs`
- Stripe webhook skeleton:
  - `POST /webhooks/stripe`
  - events handled:
    - `checkout.session.completed`
    - `invoice.paid`
    - `customer.subscription.deleted`
- Plan limit enforcement on:
  - `POST /projects`
  - `POST /posts`
  - connector add flows (`POST /channels` and social OAuth starts/callbacks)
- Daily quota maintenance task:
  - `workers.tasks.reset_monthly_post_usage`

Plan limit response:
```json
{
  "error_code": "PLAN_LIMIT_EXCEEDED",
  "message": "Upgrade your plan."
}
```

Cookie mode (feature flag):
- `AUTH_USE_HTTPONLY_COOKIES=true` enables access-token cookie
- cookie settings:
  - `AUTH_COOKIE_SECURE`
  - `AUTH_COOKIE_SAMESITE`
  - `AUTH_COOKIE_DOMAIN`

Production files:
- `docker-compose.prod.yml`
- `deploy/nginx/nginx.prod.conf`
- `backend/Dockerfile.prod`
- `dashboard/Dockerfile.prod`
- `.env.production`

### Required Env Vars (Wave 3)

- `STRIPE_API_KEY`
- `STRIPE_WEBHOOK_SECRET`
- `AUTH_USE_HTTPONLY_COOKIES`
- `AUTH_COOKIE_SECURE`
- `AUTH_COOKIE_SAMESITE`
- `AUTH_COOKIE_DOMAIN`

### Stripe Integration Checklist

1. Create products/plans in Stripe matching your `subscription_plans`.
2. Configure webhook endpoint:
   - `https://<your-domain>/api/webhooks/stripe`
3. Enable events:
   - `checkout.session.completed`
   - `invoice.paid`
   - `customer.subscription.deleted`
4. Set `STRIPE_WEBHOOK_SECRET` in runtime env.
5. Ensure checkout session metadata includes `company_id` (and optional `plan_name`).

### Production Deployment

1. Fill `.env.production` with strong secrets and real domains.
2. Build and run:
   - `docker compose -f docker-compose.prod.yml up --build -d`
3. Verify:
   - `GET http://<host>/api/health`
   - `GET http://<host>/api/ready`
   - dashboard loads on `http://<host>/`

## Phase 7.0 - Release Readiness

Wave 7.0 introduces release readiness guardrails without breaking existing contracts.

### Staging parity

Environment templates:
- `.env.production`
- `.env.staging`
- `dashboard/.env.staging`

### Migration lockfile strategy

To prevent concurrent migration upgrades:
- lock script: `backend/scripts/migrate_with_lock.sh`
- lock file: `/tmp/control-center-alembic.lock` (configurable with `ALEMBIC_LOCK_FILE`)
- timeout: `ALEMBIC_LOCK_TIMEOUT_SECONDS` (default `120`)

`docker-compose.yml` and `backend/Dockerfile.prod` now run migrations through the lock script.

### Smoke tests

Root scripts:
- `scripts/smoke_api.sh`
- `scripts/smoke_dashboard.sh`
- `scripts/smoke_all.sh`
- `scripts/preflight_check.sh`

`scripts/smoke_api.sh` validates:
- `/health`
- `/ready`
- `/metrics`
- signup/login workflow
- project/channel/post create workflow

`scripts/smoke_dashboard.sh` validates:
- dashboard root responds with HTTP 200
- frontend mount point exists

### Preflight checklist

Run:

```bash
sh scripts/preflight_check.sh
```

Checks:
1. API `/health`
2. Startup dependencies:
   - database up
   - redis up
   - worker heartbeat present
3. API `/ready`
4. API smoke workflow
5. Dashboard smoke workflow

## Phase 7.1 - CI/CD and Deployment Pipeline

Added pipeline file:
- `.github/workflows/deploy.yml`

Pipeline stages:
- backend deps + alembic upgrade + `pytest`
- dashboard lint + build
- docker image builds + smoke run (`scripts/smoke_all.sh`)
- image publish on `main`
- staging deploy on `dev`
- production deploy on tags `v*`

Deployment script:
- `scripts/deploy.sh <staging|production>`

Rollback strategy:
1. Redeploy previous image tags for backend/dashboard.
2. Re-run compose with previous tags.
3. If rollback requires schema compatibility, run matching alembic downgrade manually for the latest additive migration.
4. Validate with `scripts/preflight_check.sh` and `scripts/smoke_all.sh`.

## Phase 7.2 - Feature Flags and Controlled Rollout

New table:
- `feature_flags`

New endpoints (tenant-scoped):
- `GET /feature-flags`
- `PATCH /feature-flags/{id}`

Behavior:
- global + per-tenant effective flag resolution
- Redis TTL cache for remote config (`FEATURE_FLAG_CACHE_TTL_SECONDS`)

## Phase 7.3 - Sales-Ready SaaS Flow

New backend endpoints:
- `GET /public/plans`
- `GET /billing/plans`
- `GET /billing/current`
- `POST /billing/checkout-session`

Dashboard additions:
- public landing page (`/`)
- public pricing page (`/pricing`)
- checkout bridge from onboarding / dashboard upsell card

Stripe env vars:
- `STRIPE_CHECKOUT_SUCCESS_URL`
- `STRIPE_CHECKOUT_CANCEL_URL`
- `STRIPE_PRICE_ID_STARTER`
- `STRIPE_PRICE_ID_PRO`
- `STRIPE_PRICE_ID_ENTERPRISE`

## Phase 7.4 - Support and Operations Admin Panel

New endpoints (platform-admin only):
- `GET /admin/tenants`
- `GET /admin/audit-logs`
- `POST /admin/tenants/{tenant_id}/impersonate`
- `GET /admin/tenants/{tenant_id}/export?format=json|csv`
- `GET /admin/webhooks/events`
- `POST /admin/webhooks/events/{event_id}/resend`

New table:
- `webhook_events`

Dashboard page:
- `/app/admin` with tenant list, audit stream and impersonation

## Phase 7.5 - AI Quality Engine

New table:
- `ai_quality_policies`

New endpoints (tenant-scoped):
- `GET /ai-quality/policy?project_id=...`
- `PATCH /ai-quality/policy?project_id=...`
- `POST /ai-quality/evaluate`
- `POST /ai-quality/variants`
- `POST /ai-quality/content/{id}/evaluate-and-attach`

Integration:
- automation content generation now attaches quality metadata when `beta_ai_quality` is enabled
- high-risk content can be forced into `needs_review`

### New Environment Variables (Phase 7.x)

- `FEATURE_FLAG_CACHE_TTL_SECONDS`
- `PLATFORM_ADMIN_EMAILS`
- `VITE_PLATFORM_ADMIN_EMAILS`

## Phase 8 - Platform Operating System

Phase 8 adds a platform-level control plane for system intelligence, self-healing, tenant risk controls, revenue awareness, and operational guardrails.

### New Migration

- `0014_phase8_ops_core`
  - `system_health`
  - `tenant_risk_scores`
  - `revenue_metrics`
  - `platform_incidents`
  - `performance_baselines`

### New Endpoints

- System intelligence:
  - `GET /system/health-score`
  - `POST /system/performance/dashboard-load`
- Risk / revenue:
  - `GET /tenants/{id}/risk-score`
  - `GET /metrics/revenue-overview` (platform-admin)
- Admin super-control:
  - `GET /admin/system/overview`
  - `GET /admin/incidents`
  - `POST /admin/incidents/{id}/resolve`
  - `POST /admin/system/global-publish-breaker`
  - `POST /admin/system/tenants/{id}/publish-breaker`
  - `POST /admin/system/maintenance-mode`
  - `POST /admin/feature-flags/override`

### Auto-Recovery Runtime

Beat schedules now include:
- `workers.tasks.platform_health_intelligence`
- `workers.tasks.refresh_tenant_risk_scores`
- `workers.tasks.refresh_revenue_intelligence`
- `workers.tasks.performance_baseline_snapshot`

Auto-recovery behaviors (feature-flagged):
- missing worker heartbeat -> platform incident
- repeated channel failures -> connector auto-disable
- high tenant risk/error rate -> temporary tenant throttle + optional tenant publish breaker
- high global publish failures -> optional global publish circuit breaker

### New Environment Variables (Phase 8)

- `SYSTEM_PUBLISH_FAILURE_ALERT_THRESHOLD` (default `0.05`)
- `SYSTEM_DB_LATENCY_ALERT_MS` (default `120`)
- `SYSTEM_WORKER_BACKLOG_ALERT_THRESHOLD` (default `100`)
- `TENANT_RISK_MANUAL_APPROVAL_THRESHOLD` (default `70`)

## V1 Finalization - Phase A

V1 Phase A focuses on activation, first value, and conversion without breaking existing API contracts.

### New Migration

- `0015_v1_activation_ux`
  - adds template-library fields to `content_templates`:
    - `category`
    - `tone`
    - `content_structure`
  - adds `billing_events` for subscription lifecycle history

### New/Extended Endpoints

- Template library (extended existing endpoint):
  - `GET /templates?project_id=...&category=...`
- Template-based post creation:
  - `POST /posts/from-template`
- Subscription lifecycle:
  - `POST /billing/upgrade`
  - `POST /billing/downgrade`
  - `POST /billing/cancel`
  - `POST /billing/reactivate`
  - `GET /billing/history`
- Extended `GET /billing/current`:
  - usage counters and usage percentages for posts/projects/connectors
  - lifecycle indicators (`in_grace_period`, `expired`, `days_left_in_period`)

### Activation Funnel (Dashboard)

1. Tenant confirmation.
2. Auto-create first project (feature-flagged path).
3. Connect first channel with recommended default.
4. Generate first post from template and immediately:
   - save draft,
   - schedule,
   - or publish now.

Onboarding progress is shown as `0% -> 25% -> 50% -> 75% -> 100%` and persisted per tenant.

### New Feature Flags (V1 A)

- `v1_onboarding_first_value`
- `v1_auto_project_after_signup`
- `v1_template_library`
- `v1_smart_tooltips`
- `v1_plan_limit_visualization`
- `v1_subscription_lifecycle_ux`
- `v1_conversion_nudges`

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
