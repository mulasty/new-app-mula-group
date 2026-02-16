# Testing Guide

Quick guide for manual and smoke testing in current test phase.

## Prerequisites

- Docker Desktop running
- Backend + dashboard started:

```bash
docker compose up --build
```

## Test Account

Use this seeded tenant user for fast QA login:

- tenant UUID: `7f855bba-10be-4410-8083-77949ba33a6b`
- email: `owner@test.local`
- password: `secret123`

## Smoke Flow (UI)

1. Open `http://localhost:3000/auth`
2. Login with credentials above
3. Verify redirect to `/app`
4. Open `/app/onboarding` and complete all 4 steps
5. Verify cards and empty states on Dashboard
6. Verify create/list flow in:
   - `/app/projects`
   - `/app/channels`
   - `/app/posts`
7. Open `/pricing` and verify plans render when `beta_public_pricing` enabled
8. Open `/app/settings` and toggle feature flags
9. If platform admin email is configured, open `/app/admin` and verify tenant list loads

## API Smoke Commands

```bash
curl http://localhost:8000/health
```

```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: 7f855bba-10be-4410-8083-77949ba33a6b" \
  -d '{"email":"owner@test.local","password":"secret123"}'
```

## Release Preflight (Phase 7.0)

Run full release readiness checks:

```bash
sh scripts/preflight_check.sh
```

Standalone smoke scripts:

```bash
sh scripts/smoke_api.sh
sh scripts/smoke_dashboard.sh
sh scripts/smoke_all.sh
sh scripts/deploy.sh staging
```

## Phase 7 Backend Tests

```bash
cd backend
pytest -q tests/test_phase7_flags_admin_ai.py
```

## Publishing Flow Smoke (Phase-4)

```bash
cd backend
python scripts/test_publish_flow.py
```

The script creates tenant/project/channel/post, schedules immediate publish, waits for worker result, and verifies:
- `/posts` status is `published`
- `/posts/{id}/timeline` contains publish events
- `/website/publications` contains the published record

## Useful Dev Commands

```bash
make dashboard-install
make dashboard-build
make dashboard-test
```

or

```bash
just dashboard-install
just dashboard-build
just dashboard-test
```
