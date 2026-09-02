# Task 2 — DRF API with JWT Auth, Per-User Logging, and Redis Caching

A Django REST Framework API demonstrating:
- JWT-authenticated endpoints (only authenticated users can access the API)
- Per-user request/response logging with timing, stored on the filesystem
- Redis-backed response caching with a dynamic cache-busting strategy

## Stack

- Django + Django REST Framework
- PostgreSQL (database)
- Redis (cache)
- JWT auth via `djangorestframework-simplejwt`
- Dockerized: `web`, `migrate`, `postgres`, `redis` services via Docker Compose

## Setup (Docker — recommended)

The stack runs out of the box with sensible defaults — **no `.env` file required** for local
use. If you want to override anything (secret key, DB credentials, Redis password, etc.),
copy `.env.example` to `.env` and adjust as needed; Docker Compose picks it up automatically.

    docker compose up --build

This brings up Postgres and Redis, runs migrations automatically (via the one-shot `migrate`
service), then starts the API on `http://localhost:8000`.

Create a user to authenticate with:

    docker compose exec web python manage.py createsuperuser

## Setup (manual, without Docker)

    python -m venv venv && source venv/bin/activate
    pip install -r requirements.txt
    docker compose up -d postgres redis   # still need these running somewhere
    python manage.py migrate
    python manage.py createsuperuser
    python manage.py runserver

## Environment Variables

All variables have working defaults for local development. Override via `.env` for anything
beyond local use (see `.env.example`).

| Variable | Default | Purpose |
|---|---|---|
| `SECRET_KEY` | `dev-only-insecure-key` | Django secret key — **must** be overridden in any non-local environment |
| `DEBUG` | `true` | Django debug mode |
| `ALLOWED_HOSTS` | `*` | Django allowed hosts |
| `DB_NAME` / `DB_USER` / `DB_PASSWORD` | `taskdb` / `taskuser` / `taskpass` | Postgres credentials |
| `REDIS_PASSWORD` | `devredispass` | Redis auth password |

## Authentication

All API endpoints require a JWT access token — enforced globally via
`DEFAULT_PERMISSION_CLASSES = IsAuthenticated` in `REST_FRAMEWORK` settings.

    # Obtain a token
    curl -X POST http://localhost:8000/api/token/ -d "username=<user>&password=<pass>"

    # Use it
    curl http://localhost:8000/api/sample-data/ -H "Authorization: Bearer <access_token>"

    # Refresh an expired access token
    curl -X POST http://localhost:8000/api/token/refresh/ -d "refresh=<refresh_token>"

Requests without a valid token receive `401 Unauthorized`.

## Request/Response Logging

Every request is logged to `logs/<username>.jsonl` (one JSON object per line) via
`api.middleware.RequestLoggingMiddleware`. Unauthenticated requests are logged under
`logs/anonymous.jsonl`. Each entry contains:

- `user`, `method`, `path`, `status_code`
- `start_time`, `end_time` (UTC, ISO 8601)
- `duration_seconds` (measured with `time.monotonic()`, immune to system clock adjustments)

## Caching & Cache-Busting

Responses from `/api/sample-data/` are cached in Redis for 60 seconds. The cache key
(`api/cache_utils.py`) is built from four independent inputs, any of which busts the cache:

1. **URL path + query parameters** — different filters/params never share a cached entry.
2. **User role** (`staff` vs regular `user`) — role-dependent responses stay separate.
3. **Time bucket** — the key changes automatically every 60 seconds, so cached data
   self-expires without manual invalidation.
4. **Explicit override** — pass `?refresh=true` to force a fresh computation regardless
   of cache state.

The response body includes `"from_cache": true/false` so cache behavior is visible and
testable directly in the response.

## Tests

    docker compose exec web python manage.py test api
    # or, without Docker:
    python manage.py test api

Covers: auth enforcement (missing/invalid token), cache hit/miss behavior across query
params and user roles, the manual `?refresh=true` override, and log file contents.

## Project Structure

    core/           # Django project settings, urls, wsgi
    api/
      views.py       # SampleDataView — the demo authenticated + cached endpoint
      middleware.py   # RequestLoggingMiddleware
      cache_utils.py  # cache key construction / cache-busting logic
      tests.py
    Dockerfile
    docker-compose.yml
    requirements.txt