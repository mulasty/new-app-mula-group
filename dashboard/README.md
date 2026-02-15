# Control Center Dashboard

SaaS dashboard frontend for Control Center.

## Run locally

```bash
cp .env.example .env
npm install
npm run dev
```

## Env

- `VITE_API_BASE_URL` default: `/api`
- `VITE_PROXY_TARGET` default: `http://localhost:8000` (used by Vite dev proxy)
- `VITE_ENABLE_MOCK_FALLBACK` default: `false` (`true` enables local mock fallback when endpoint returns 404/405/501)

## Test Phase Note

During current test phase, login autofill is enabled in dev localhost mode for faster QA.

## Onboarding flow

- Route: `/app/onboarding`
- Progress: 4 steps (Tenant -> Project -> Channel -> Post)
- State persistence:
  - localStorage (`cc_onboarding_state`)
  - URL query (`?step=1..4`)
- Skip is allowed (`Skip for now`) and soft reminder appears on Dashboard.

## Publishing console (Phase-4.1)

- Posts page includes:
  - status filters (`draft`, `scheduled`, `publishing`, `published`, `failed`)
  - title search + sorting (`publish_at`, `updated_at`)
  - actions: edit, schedule/reschedule, publish now, cancel schedule, retry failed, timeline drawer
  - tabs: `Posts` and `Website feed`
- Dashboard includes:
  - per-project KPI cards (scheduled/published/failed)
  - recent publish activity based on timeline events
- Channels page is project-scoped for website channel connection.

## API fallback behavior

Dashboard attempts backend endpoints first and uses local mock fallback when missing:

- `/projects`
- `/channels`
- `/posts`
- `/website/publications`
- `/posts/{id}/timeline`

When fallback is active, UI shows clear warning banners and `mock` badges.

## UX polish included

- Global route loading bar
- Tenant switcher modal with UUID validation
- Logout confirmation modal
- Command palette (`Ctrl+K`) for quick navigation
- Inactivity auto-logout (12h)
- Standardized components: `PageHeader`, `EmptyState`, `Modal`, `Spinner`
