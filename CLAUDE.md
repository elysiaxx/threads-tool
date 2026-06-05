# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project layout

The application source lives in `files/threads-tool/threads-tool/`. The `files/threads_env/` directory is a local Python venv used only for ad-hoc scripts; the main app runs entirely inside Docker.

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
- MinIO console: `http://localhost:9001` (create bucket `media`, set public-read)
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
| `app/services/storage.py` | S3-compatible upload with prefix `media/{user_id}/...` |
| `app/workers/tasks.py` | Celery task stubs (Collector + Analytics, not yet implemented) |
| `app/config.py` | All settings via `pydantic-settings` / `.env` |

## Module status

- **Auth + multi-tenancy**: complete (register, login, JWT, accounts OAuth).
- **Collector** (`app/modules/collector/`): stub — `collect_media` task raises `NotImplementedError`.
- **Analytics** (`app/modules/analytics/`): stub — `poll_account_metrics` and `poll_tracked` raise `NotImplementedError`.
- **Publisher**: not started.

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
