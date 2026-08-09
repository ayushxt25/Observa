# Observa Backend

FastAPI backend foundation for Observa telemetry ingestion, persistence, query, aggregation, and Redis-backed publish flow.

The frontend simulator remains active in this phase. This backend is intentionally ready for a future remote telemetry source without changing the existing chart components.

## Stack

- FastAPI
- PostgreSQL
- SQLAlchemy 2.x
- Alembic
- Redis Streams
- Pydantic v2
- Uvicorn
- Pytest
- Docker Compose

## Architecture

```text
Telemetry API
  -> Pydantic validation
  -> IngestionService
  -> TelemetryRepository
  -> PostgreSQL telemetry_events
  -> TelemetryBroker
  -> Redis Stream telemetry:events

Metric API
  -> Metric validation
  -> MetricsService
  -> SQL aggregation/query
  -> typed JSON response

Dashboard API
  -> Pydantic config validation
  -> DashboardRepository
  -> PostgreSQL dashboards/dashboard_widgets
  -> typed JSON response

Alert API
  -> AlertRepository
  -> AlertEvaluationService
  -> PostgreSQL alert_rules/incidents
  -> Celery periodic evaluation via Redis broker

Auth API
  -> AuthRepository
  -> PostgreSQL users/workspaces/memberships/auth_sessions
  -> JWT access tokens + hashed refresh sessions
```

## Docker Startup

From the repository root:

```powershell
docker compose up --build
```

The backend is exposed at `http://localhost:8001` through Docker Compose. API documentation is available at `http://localhost:8001/docs`.

## Local Python Startup

From `backend/`:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
alembic upgrade head
uvicorn app.main:app --reload
```

Local startup expects PostgreSQL and Redis to be reachable through `.env`.

## Migrations

```powershell
alembic upgrade head
alembic current
```

Migration `0001` creates `telemetry_events` and indexes common time/service/region query paths. Migration `0002` creates `dashboards` and `dashboard_widgets` with cascade delete and widget-order indexes. Migration `0003` creates `alert_rules` and `incidents`, including a partial unique index for one active firing incident per rule.
Migration `0004` creates users, workspaces, memberships and auth sessions, then backfills existing development dashboards and alert rules into a default workspace without touching telemetry history.

## Seed Data

```powershell
python -m scripts.generate_telemetry --count 10000 --batch-size 500 --seed 42
```

The generator posts realistic deterministic telemetry to the batch ingestion endpoint.

## Endpoints

- `GET /health`
- `GET /ready`
- `POST /api/v1/telemetry`
- `POST /api/v1/telemetry/batch`
- `GET /api/v1/telemetry`
- `GET /api/v1/telemetry/stream/cursor`
- `GET /api/v1/telemetry/stream`
- `GET /api/v1/metrics/query`
- `GET /api/v1/services`
- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/refresh`
- `POST /api/v1/auth/logout`
- `GET /api/v1/auth/me`
- `GET /api/v1/workspaces`
- `POST /api/v1/workspaces`
- `GET /api/v1/workspaces/{id}`
- `PATCH /api/v1/workspaces/{id}`
- `GET /api/v1/workspaces/{id}/members`
- `POST /api/v1/workspaces/{id}/members`
- `PATCH /api/v1/workspaces/{id}/members/{user_id}`
- `GET /api/v1/dashboards`
- `POST /api/v1/dashboards`
- `GET /api/v1/dashboards/{id}`
- `PATCH /api/v1/dashboards/{id}`
- `DELETE /api/v1/dashboards/{id}`
- `POST /api/v1/dashboards/{id}/widgets`
- `PATCH /api/v1/dashboards/{id}/widgets/{widget_id}`
- `DELETE /api/v1/dashboards/{id}/widgets/{widget_id}`
- `GET /api/v1/alerts`
- `POST /api/v1/alerts`
- `GET /api/v1/alerts/{id}`
- `PATCH /api/v1/alerts/{id}`
- `DELETE /api/v1/alerts/{id}`
- `POST /api/v1/alerts/{id}/evaluate`
- `GET /api/v1/incidents`
- `GET /api/v1/incidents/{id}`

The API uses camelCase JSON to align with the frontend domain, while Python models use snake_case internally.
Live SSE reads from Redis Streams; historical HTTP reads remain PostgreSQL-backed.
Dashboard endpoints persist view configuration only; they do not store telemetry samples or create live streams.

## Alert Evaluation

Celery beat runs one periodic scan task, `alerts.evaluate_due_rules`, every 5 seconds by default. Alert rule intervals have a 5-second minimum, and the scan evaluates only enabled rules whose interval has elapsed. The worker reads PostgreSQL metrics through the existing telemetry repository and writes alert state plus incident transitions transactionally. Redis/Celery outages pause evaluation only; telemetry ingestion, historical reads and SSE live delivery remain independent.

## Authentication And RBAC

The backend uses email/password registration and login. Passwords are hashed with bcrypt through Passlib. Access tokens are short-lived JWTs with explicit access-token type, issuer, audience and subject claims. Refresh tokens are opaque random values stored only as SHA-256 hashes in `auth_sessions`; refresh rotates the session and logout revokes the current refresh token. Register, login and refresh endpoints use a small Redis-backed per-IP rate limiter. If Redis is unavailable, rate limiting fails open and logs a warning so normal auth does not hard-fail during Redis outages.

Workspace-scoped APIs require `Authorization: Bearer <accessToken>` and usually `X-Workspace-Id`. If no workspace header is supplied, the first membership is used. Dashboards, alert rules and incidents are tenant-scoped; telemetry events are not workspace-scoped yet. Role order is `viewer < member < admin < owner`, with final-owner demotion and removal blocked.

## Tests

```powershell
pytest
```

Tests use dependency overrides and pure validation/service checks so they do not require a production database.
