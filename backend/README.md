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
Live SSE reads from workspace Redis Streams; historical HTTP reads remain PostgreSQL-backed and workspace-filtered. Machine ingestion uses `Authorization: Bearer <workspace API key>` or `X-Observa-Api-Key`, and the backend derives `workspace_id` from the key.
Dashboard endpoints persist view configuration only; they do not store telemetry samples or create live streams.

## Alert Evaluation

Celery beat runs one periodic scan task, `alerts.evaluate_due_rules`, every 5 seconds by default. Alert rule intervals have a 5-second minimum, and the scan evaluates only enabled rules whose interval has elapsed. The worker reads PostgreSQL metrics through the existing telemetry repository and writes alert state plus incident transitions transactionally. Redis/Celery outages pause evaluation only; telemetry ingestion, historical reads and SSE live delivery remain independent.

## Authentication And RBAC

The backend uses email/password registration and login. Passwords are hashed with bcrypt through Passlib. Access tokens are short-lived JWTs with explicit access-token type, issuer, audience and subject claims. Refresh tokens are opaque random values stored only as SHA-256 hashes in `auth_sessions`; refresh rotates the session and logout revokes the current refresh token. Register, login and refresh endpoints use a small Redis-backed per-IP rate limiter. If Redis is unavailable, rate limiting fails open and logs a warning so normal auth does not hard-fail during Redis outages.

Workspace-scoped APIs require `Authorization: Bearer <accessToken>` and usually `X-Workspace-Id`. If no workspace header is supplied, the first membership is used. Dashboards, alert rules, incidents and telemetry reads are tenant-scoped. Role order is `viewer < member < admin < owner`, with final-owner demotion and removal blocked.

Phase 8 also scopes telemetry reads, services, metrics and SSE to the active workspace. Workspace API keys are stored only as hashes, shown once on creation, revocable by owner/admin, and protected by a lightweight per-key ingestion rate limit.

Phase 9 adds alert notification delivery. Notification channels are workspace-scoped and currently support `email` and generic `webhook`. Alert rules can attach multiple channels. When an incident opens or resolves, alert evaluation writes durable pending delivery rows and then queues Celery delivery tasks after commit. A retry scanner (`notifications.retry_due`) requeues pending retryable deliveries and recovers stale `delivering` rows after `NOTIFICATION_DELIVERY_LEASE_SECONDS`, so Redis/Celery outages do not lose delivery intent.

Webhook delivery sends JSON with alert, incident, metric, value and threshold context plus a stable `deliveryId`. If a signing secret is configured, the worker signs `timestamp + "." + rawBody` with HMAC-SHA256 and sends `X-Observa-Delivery-Id`, `X-Observa-Signature: sha256=<hex>` and `X-Observa-Timestamp`. Delivery is at-least-once; webhook consumers should deduplicate by delivery id. Secrets are encrypted at rest with `NOTIFICATION_SECRET_KEY` and are never returned in API responses. Production SSRF protection blocks non-HTTPS and private/loopback/link-local destinations; Docker development explicitly sets `WEBHOOK_ALLOW_PRIVATE_NETWORKS=true` for local receivers. DNS is validated before request and redirects are disabled; DNS rebinding between validation and the HTTP client's connection remains a documented residual risk.

Phase 10 adds durable audit events for authenticated mutations. `GET /api/v1/audit-events` and `GET /api/v1/audit-events/{id}` are workspace-scoped and owner/admin-only. The backend emits a server-generated `X-Request-Id` header and stores that request id with audit rows. Mandatory product mutation audits are written in the same database transaction as their domain mutation, so an audit insert failure rolls the mutation back. Auth success/failure events and manual alert evaluation audit are recorded after their underlying auth/evaluation operation. Audit metadata is built from safe identifiers and changed-field summaries, then recursively redacted before insert; there are no update or delete endpoints for audit events.

Email delivery uses SMTP settings (`SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_TLS`). Missing SMTP configuration leaves delivery rows retryable instead of dropping them.

## Tests

```powershell
pytest
```

Tests use dependency overrides and pure validation/service checks so they do not require a production database.
