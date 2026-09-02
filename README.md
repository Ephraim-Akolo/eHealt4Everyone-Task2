# Task 2 — DRF API with JWT Auth, Per-User Logging, and Redis Caching

## Setup

    python -m venv venv && source venv/bin/activate
    pip install -r requirements.txt
    cp .env.example .env   # set REDIS_URL if not using the default
    python manage.py migrate
    python manage.py createsuperuser

Redis via Docker (if not running one locally):

    docker compose up -d redis

Run the server:

    python manage.py runserver

## Authentication

All endpoints require a JWT access token (only exception: obtaining/refreshing the token itself).

    curl -X POST http://localhost:8000/api/token/ -d "username=<user>&password=<pass>"
    curl http://localhost:8000/api/sample-data/ -H "Authorization: Bearer <access_token>"

Requests without a valid token receive `401 Unauthorized`.

## Request/Response Logging

Every request is logged to `logs/<username>.jsonl` (one JSON object per line) via
`api.middleware.RequestLoggingMiddleware`. Unauthenticated requests are logged under
`logs/anonymous.jsonl`. Each entry contains:

- `user`, `method`, `path`, `status_code`
- `start_time`, `end_time` (UTC, ISO 8601)
- `duration_seconds` (measured with `time.monotonic()`, immune to clock adjustments)

## Caching & Cache-Busting

Responses from `/api/sample-data/` are cached in Redis for 60 seconds. The cache key
(`api/cache_utils.py`) is built from four independent inputs, any of which busts the cache:

1. **URL path + query parameters** — different filters/params never share a cached entry.
2. **User role** (`staff` vs regular `user`) — role-dependent responses stay separate.
3. **Time bucket** — the key changes automatically every 60 seconds, so cached data
   self-expires without manual invalidation.
4. **Explicit override** — pass `?refresh=true` to force a fresh computation regardless
   of cache state.

The response body includes `"from_cache": true/false` so cache behavior is visible
and testable.

## Tests

    python manage.py test api

Covers: auth enforcement (missing/invalid token), cache hit/miss behavior across
params and roles, the manual refresh override, and log file contents.

