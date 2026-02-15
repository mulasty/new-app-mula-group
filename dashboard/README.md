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

## Analytics (Phase-4.2)

- Dashboard tabs: `Overview | Publishing | Activity`
- Analytics data sources:
  - `/analytics/publishing-summary`
  - `/analytics/publishing-timeseries` (7d/30d/90d)
  - `/analytics/activity-stream`
- Queries refresh every 60 seconds and are invalidated after post mutations.
- Components:
  - `AnalyticsKpiCards`
  - `PublishingChart`
  - `ActivityStream`

## LinkedIn connector (Phase-5.1)

- Channels page includes `Connect LinkedIn` OAuth flow.
- UI states:
  - `Connecting LinkedIn...`
  - success (`Connected`)
  - error banner with callback reason.
- LinkedIn channels render with `in` badge and connected status.

## Meta connector (Phase-5.3)

- Channels page includes `Connect Facebook / Instagram` OAuth action.
- Meta callback feedback:
  - `connected=meta` success notification
  - `connected=meta_error` with clear reason banner
- Connected entities panel:
  - Facebook pages list
  - Instagram business accounts list
- Publishing target control:
  - channel toggles (`active` / `disabled`) from Posts page
  - only active channels receive publish jobs
- Timeline view surfaces:
  - publish latency (`publish_latency_ms`)
  - adapter type
  - retry attempts and retryable flag

## Universal connector UX (Phase-5.4)

- Dynamic `Connect Platform` modal reads from `GET /connectors/available`.
- Connector list supports available + unavailable platforms (`coming soon` style).
- Capability badges can render:
  - `Text`
  - `Image`
  - `Video`
  - `Reels`
  - `Shorts`

## Multi-platform connector UI (Phase-5.5)

- Channels page now supports OAuth connect flows for:
  - TikTok
  - Threads
  - X
  - Pinterest
- Callback query handling supports:
  - `?connected=<platform>`
  - `?connected=<platform>_error&reason=...`
- Channel cards include:
  - platform icon badge
  - connection status (`Connected`, `Needs reconnect`, `Disabled`)
  - capability badges from `capabilities_json`

## Connector Framework (Phase-5.2)

- Channels page renders capability badges from backend:
  - `Text`
  - `Image`
  - `Video`
- Posts console blocks text publishing actions when selected project has no text-capable channel.
- Timeline drawer highlights per-channel publish telemetry:
  - adapter type
  - latency (`publish_duration_ms`)
  - retryability + attempt number

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
