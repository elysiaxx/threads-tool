# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project layout

The backend source lives in `files/threads-tool/threads-tool/` (FastAPI under `app/`). The React frontend lives in `files/threads-tool/threads-tool/web/` (Vite + TypeScript + Tailwind). The `files/threads_env/` directory is a local Python venv used only for ad-hoc scripts; the main app runs entirely inside Docker.

### Frontend (`web/`)

Vite + React 18 + TypeScript + Tailwind + React Router + React Query (data fetching/polling) + Recharts (charts). Run from `web/`:

```bash
npm install
npm run dev      # http://localhost:5173 — proxies /api to the backend on :8000
npm run build    # tsc --noEmit + vite build -> dist/
```

- API client (`src/api/client.ts`) attaches the JWT from `localStorage` and clears it on 401.
- `VITE_API_BASE` (in `.env`) overrides the API base; empty means `/api` via the Vite dev proxy.
- Pages: Login, Register, Accounts (OAuth connect + tracked accounts + poll), Sources (add media + auto-refresh status), Analytics (charts + keyword search + trends/posts).
- OAuth from the SPA uses `GET /accounts/oauth/{platform}/authorize-url` (returns the authorize URL as JSON) because a full-page redirect can't carry the `Authorization` header.

## Common commands

All commands should be run from `files/threads-tool/threads-tool/`.

```bash
# First-time setup — generate a Fernet key for TOKEN_ENCRYPTION_KEY in .env
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

cp .env.example .env   # then fill in the key above + Meta app credentials

# Start everything (API, Celery worker, Celery Beat, Mongo, Redis, MinIO)
docker compose up --build

# Stop
docker compose down
```

Services after startup:
- API + Swagger: `http://localhost:8000` / `/docs`
- MinIO console: `http://localhost:9001` (bucket `media` is auto-created with a public-read policy at API startup via `storage.ensure_bucket`)
- MongoDB: `localhost:27017`, Redis: `localhost:6379`

Quick auth smoke-test:
```bash
curl -X POST localhost:8000/api/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"a@b.com","password":"password123"}'

curl -X POST localhost:8000/api/auth/login \
  -d 'username=a@b.com&password=password123'

curl localhost:8000/api/accounts \
  -H "Authorization: Bearer <TOKEN>"
```

## Architecture

```
Web UI (React)  →  FastAPI (app/)  →  MongoDB (motor, async)
                                   →  Redis + Celery (workers/)
                                   →  MinIO / S3 (services/storage.py)
                                   →  Threads Graph API (services/oauth/threads.py)
```

Celery handles all heavy/long tasks (media download, publish, periodic metric polling) so the API stays fast. Celery Beat drives scheduled polling.

## Critical pattern: multi-tenancy via TenantRepository

Every user-owned collection (`accounts`, `sources`, `jobs`, `posts`, `searches`, `trends`) **must** be accessed only through `TenantRepository` (`app/db/repository.py`). It hard-injects `user_id` into every read filter and every written document. Bypassing it and touching a raw Motor collection is a data-leak bug.

In routes, get repositories via the `RepoFactory` dependency:
```python
@router.get("")
async def list_posts(repos: RepoFactory = Depends(get_repos)):
    posts = repos("posts")          # scoped TenantRepository
    return await posts.find_many()
```

`get_repos` (`app/core/deps.py`) chains JWT decode → `CurrentUser` → `RepoFactory` bound to that `user_id`. The OAuth callback is the one exception: it receives `user_id` from the signed `state` token instead of a JWT.

## Key files

| File | Role |
|---|---|
| `app/db/repository.py` | `TenantRepository` — the data-isolation boundary |
| `app/core/deps.py` | JWT → `get_current_user` + `RepoFactory` DI |
| `app/core/security.py` | Password hash, JWT creation/decode, OAuth state token |
| `app/core/crypto.py` | Fernet encryption/decryption for Threads access tokens |
| `app/db/indexes.py` | MongoDB indexes (always start with `user_id`) + `metrics_ts` time-series collection |
| `app/services/oauth/threads.py` | Threads OAuth: authorize URL, code exchange, token refresh |
| `app/services/threads_api.py` | Threads Graph API read client (threads list, insights, keyword search) |
| `app/services/proxy.py` | Proxy resolution (per-account fixed → rotating pool fallback) + connection test |
| `app/services/storage.py` | S3-compatible upload with prefix `media/{user_id}/...` |
| `app/workers/tasks.py` | Celery tasks: `collect_media`, `poll_account_metrics`, `poll_tracked`, Beat dispatcher |
| `app/config.py` | All settings via `pydantic-settings` / `.env` |

## Module status

- **Auth + multi-tenancy**: complete (register, login, JWT, accounts OAuth).
- **Collector** (`app/modules/collector/`): complete — `collect_source` downloads a public URL to storage and updates `sources`; `POST/GET /api/sources`.
- **Analytics** (`app/modules/analytics/`): complete — `poll_account` writes account/post insights to `metrics_ts` + upserts `posts`; `poll_tracked` runs keyword search into `trends`. Celery Beat fans out `dispatch_owned_accounts` every 30 min. Routes under `/api/analytics`.
- **Proxy** (`app/services/proxy.py`): complete — `proxies` collection (passwords Fernet-encrypted), CRUD + connection test at `/api/proxies`, per-account assignment via `PATCH /api/accounts/{id}/proxy`. Resolution model: an account's `proxy_id` wins, else a random `active` proxy from the user's pool. Gated by `PROXY_ENABLED`; `PROXY_APPLY_TO_MEDIA` toggles whether Collector downloads are proxied. Wired into `ThreadsApiClient`, the OAuth provider, and the collector via httpx `proxy=`.
- **Publisher** (`app/modules/publisher/`): complete — `publish_job` runs the Threads 2-step flow (create container → poll until `FINISHED` → `threads_publish`) for TEXT/IMAGE/VIDEO/CAROUSEL, then writes the result to `posts`. Jobs live in the `jobs` collection; `POST /api/publish` creates one (immediate or scheduled), `POST /api/publish/{id}/retry` re-runs a failed one. Scheduled posts are dispatched by the `publisher.dispatch_due_jobs` Beat task (every 1 min) which flips due `scheduled` jobs to `pending` and enqueues `publisher.publish`.
- **Frontend** (`web/`): complete — Login/Register, Accounts (+ proxy assignment), Sources, Publish (compose + media picker + schedule + job queue), Analytics dashboard, Proxies (CRUD + test).

> Async-in-Celery pattern: each task opens its own short-lived motor client and runs the async service via `asyncio.run` (see `app/workers/tasks.py`), avoiding the API's shared event loop. `metrics_ts` is written directly (not via `TenantRepository`) because `user_id`/`post_id` must live in the time-series `meta` field; reads (`GET /api/analytics/metrics`) likewise query `metrics_ts` directly but force-filter `meta.user_id`.

> Retry: network/5xx/429 failures are wrapped as `http_retry.TransientError` and retried by Celery (`autoretry_for` + exponential backoff, see `_RETRY` in `app/workers/tasks.py`); terminal errors are recorded as `failed` and not retried. Token refresh: `auth.dispatch_token_refresh` Beat task (every 12h) refreshes owned-account tokens within `TOKEN_REFRESH_THRESHOLD_DAYS` of expiry; `POST /api/accounts/{id}/refresh-token` does it on demand.

## Threads API constraints

- **Media must be a public URL**: the API fetches media from the URL you provide; direct upload is not possible. MinIO/S3 bucket must be public-read.
- **Token lifetime**: ~60 days. Logic to refresh before expiry is needed (`ThreadsOAuthProvider.refresh()`).
- **Post limit**: ~250 posts / 24 h per user account.
- **Search endpoint**: heavily rate-limited — cache results aggressively.
- **Insights**: data only available from 2024-04-13; demographics require >100 followers.
- **App review**: `threads_content_publish` requires Meta Tech Provider Verification before production use.
- **Media formats**: images JPEG/PNG ≤ 8 MB, 320–1440 px wide; video MP4/MOV ≤ 5 min / 1 GB; carousel max 10 items.

## Data model rules

- All compound MongoDB indexes must start with `user_id` (matches `TenantRepository` query pattern).
- `metrics_ts` is a MongoDB time-series collection; `user_id` and `post_id` live in the `meta` field.
- Access tokens are stored encrypted (`access_token_enc` via `crypto.encrypt_token`), never plaintext.
- Storage objects use prefix `media/{user_id}/` for clean per-user lifecycle management.
- Every Celery task must accept `user_id` as a parameter to fetch the correct token and write to the correct tenant.
