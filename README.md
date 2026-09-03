# Task API

A Django REST Framework API with JWT authentication, per-user file-based
request logging, and Redis-backed response caching with dynamic
cache-busting.

## Stack

- Django 5.1 + Django REST Framework
- JWT auth via `djangorestframework-simplejwt`
- PostgreSQL (via `docker-compose`)
- Redis, for both response caching and cache-version counters
- Gunicorn

## Run it

```bash
# test environmental variables are used by default. For custom values, copy or run "cp .env.example .env", then edit the values.
docker compose up --build

# to create superuser (admin user)
docker compose exec web bash
python manage.py createsuperuser
```

This starts, in order: `postgres` → `migrate` (runs migrations +
collectstatic, then exits) → `redis` and `web` (the API on
`http://localhost:8000`).

## Auth

All endpoints under `/api/v1/` require a valid JWT **except** registration.

Examples (You need curl to test the api using this method):
```bash
# Register
curl -X POST localhost:8000/api/v1/auth/register/ \
  -H "Content-Type: application/json" \
  -d '{"username": "alice", "email": "alice@example.com", "password": "s3cur3-pass!", "role": "member"}'

# Log in -> get access + refresh tokens
curl -X POST localhost:8000/api/v1/auth/token/ \
  -H "Content-Type: application/json" \
  -d '{"username": "alice", "password": "s3cur3-pass!"}'

# Use the access token
curl localhost:8000/api/v1/tasks/ -H "Authorization: Bearer <access_token>"

# Refresh
curl -X POST localhost:8000/api/v1/auth/token/refresh/ \
  -H "Content-Type: application/json" \
  -d '{"refresh": "<refresh_token>"}'

# Create a task
curl -X POST localhost:8000/api/v1/tasks/ \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"title": "Write project report", "description": "Summarize Q3 findings", "status": "todo"}'

# List tasks
curl localhost:8000/api/v1/tasks/ -H "Authorization: Bearer <access_token>"

# List tasks, filtered by status
curl "localhost:8000/api/v1/tasks/?status=todo" -H "Authorization: Bearer <access_token>"

# List tasks, bypassing the cache
curl "localhost:8000/api/v1/tasks/?nocache=1" -H "Authorization: Bearer <access_token>"

# Retrieve a single task
curl localhost:8000/api/v1/tasks/1/ -H "Authorization: Bearer <access_token>"

# Update a task (partial update)
curl -X PATCH localhost:8000/api/v1/tasks/1/ \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"status": "in_progress"}'

# Delete a task
curl -X DELETE localhost:8000/api/v1/tasks/1/ -H "Authorization: Bearer <access_token>"

# Check own profile/role
curl localhost:8000/api/v1/auth/me/ -H "Authorization: Bearer <access_token>"
```

`role` is one of `member` (default, sees only their own tasks), `manager`
(same as member for now — a hook for future permission tiers), or `admin`
(sees and can modify every user's tasks).

## Tasks API

Standard REST/DRF ViewSet at `/api/v1/tasks/`:

| Method | Path              | Notes                                |
|--------|-------------------|---------------------------------------|
| GET    | `/api/v1/tasks/`     | List (cached)             |
| POST   | `/api/v1/tasks/`     | Create (owner = current user)         |
| GET    | `/api/v1/tasks/{id}/`| Retrieve (owner or admin only)        |
| PATCH  | `/api/v1/tasks/{id}/`| Update (owner or admin only)          |
| DELETE | `/api/v1/tasks/{id}/`| Delete (owner or admin only)          |

`GET /api/v1/tasks/?status=done` filters by status
(`todo` / `in_progress` / `done`).

## Request/response logging

`api/middleware.py`'s `RequestLoggingMiddleware` writes one JSON object
per line to `logs/<username>.log` (`logs/anonymous.log` for
unauthenticated requests) for **every** request, containing:

```json
{
  "start_time": "2026-09-02T10:15:03.120+00:00",
  "end_time": "2026-09-02T10:15:03.145+00:00",
  "duration_ms": 25.4,
  "user": "alice",
  "method": "GET",
  "path": "/api/v1/tasks/",
  "query_params": {"status": "done"},
  "status_code": 200,
  "request_body": null,
  "response_body": {"...": "..."},
  "remote_addr": "172.19.0.1"
}
```

Passwords/tokens in request/response bodies are redacted before writing.
The `logs/` directory is inside the mounted volume, so entries persist on
the host across container restarts. This is deliberately simple
(append-only text files) per the assignment; for real production use
you'd ship these to something like structured logging + an aggregator
instead of local files, and rotate/size-cap the files.

## Caching + cache-busting

`GET /api/v1/tasks/` responses are cached in Redis
(`api/cache_utils.py`, wired up in `api/views.py`). A cached entry is
only reused if **all** of these match, giving three independent
cache-busting dimensions:

1. **URL parameters** — `?status=done` and `?status=todo` (and plain
   `/api/v1/tasks/`) are cached separately.
2. **User + role** — each user has their own cache namespace, and an
   `admin` (who sees everyone's tasks) never reads a `member`'s cached
   response even for the same URL.
3. **Time** — a rolling 5-minute time bucket is folded into the key, so
   even a leftover cache entry expires within that window regardless of
   anything else.

On top of that, any write (`POST`/`PATCH`/`DELETE`) immediately bumps a
per-user version counter in Redis, which invalidates all of that user's
previously cached list responses right away rather than waiting for the
time bucket — you don't need to wait 5 minutes to see your own new task.

For manual busting, add `?nocache=1` to any `GET /api/v1/tasks/` request to
force a fresh read and re-cache it.

## Local dev without Docker

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then edit the values, especially SECRET_KEY / passwords
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```
