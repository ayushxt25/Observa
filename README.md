# Observa

Observa is a production-oriented full-stack observability platform for ingesting, querying, visualizing, alerting on, and analyzing telemetry across workspaces and services. It combines a Next.js dashboard with a FastAPI backend, PostgreSQL, Redis, Celery, authenticated SSE streams, and a reusable telemetry Query Engine.

`Next.js 16` `React 19` `TypeScript` `FastAPI` `PostgreSQL` `Redis` `Celery` `Canvas` `SVG`

## Live Demo

- Frontend: [https://performance-dashboard-rose.vercel.app](https://performance-dashboard-rose.vercel.app)
- API base URL: `https://observa-production-d905.up.railway.app`
- API docs: [https://observa-production-d905.up.railway.app/docs](https://observa-production-d905.up.railway.app/docs)
- Repository: [https://github.com/ayushxt25/Observa](https://github.com/ayushxt25/Observa)

Users can create an account in the live demo. Registration creates a default workspace and owner membership.

## Screenshots

![Observa dashboard overview](public/screenshots/dashboard-overview.png)

Live telemetry dashboard with stream controls, KPI cards, custom charts, and the performance monitor.

![Observa stress-test mode](public/screenshots/stress-test.png)

Stress-test mode using the same dashboard UI and retained telemetry controls.

![Observa mobile dashboard](public/screenshots/mobile-dashboard.png)

Responsive mobile dashboard layout.

![Observa virtualized table](public/screenshots/virtualized-table.png)

Raw telemetry table with custom virtual scrolling.

## What Observa Does

- Workspace-based authentication, membership, ownership, and RBAC.
- Email/password auth with short-lived access JWTs and HttpOnly refresh sessions.
- Workspace API keys for machine telemetry ingestion.
- Workspace-scoped telemetry persistence in PostgreSQL.
- Authenticated workspace SSE streams backed by Redis Streams.
- Persisted configurable dashboards and widgets.
- Custom Canvas/SVG line, bar, scatter, heatmap, stat, and table views.
- PostgreSQL Query Engine for historical metrics, buckets, groups, and percentiles.
- Redis-backed Query Engine cache for public historical queries.
- Alert rules, incidents, cooldown behavior, and concurrency-safe transitions.
- Durable email/webhook notification channels and delivery history.
- Append-oriented audit logging for security-sensitive and product mutations.
- Service Catalog with metadata, health summaries, dependencies, and topology.
- Incident timeline and dependency-aware blast-radius analysis.

## Architecture

```text
Vercel / Next.js
        |
        v
Railway / FastAPI
        |
        +--> PostgreSQL
        |       source of truth for users, workspaces, telemetry,
        |       dashboards, alerts, incidents, services, audit logs
        |
        +--> Redis
        |       workspace SSE streams, rate limits, query cache,
        |       Celery broker/result backend
        |
        +--> Celery worker / beat
                scheduled alert evaluation, notification delivery,
                retry scanning
```

PostgreSQL is the durable source of truth. Redis is used for bounded live telemetry streams, short-lived query caching, rate limiting, and background task coordination. Celery runs scheduled alert evaluation and asynchronous notification delivery so network calls are not performed inside request/alert transition paths.

The frontend consumes live telemetry through authenticated fetch-based SSE and uses the backend Query Engine for historical dashboard Line, Stat, and supported Bar queries. Short live windows, Scatter, and Heatmap continue to use the local `TelemetryStore` path.

## Core Technical Highlights

- Server-side workspace isolation on dashboard, widget, alert, incident, service, audit, notification, and telemetry APIs.
- API-key ingestion derives workspace identity from the key; clients cannot submit arbitrary `workspaceId`.
- Authenticated SSE uses access tokens and active workspace headers; telemetry stream IDs are separate from telemetry event IDs.
- Query Engine supports allowlisted metrics, fixed bucket sizes, optional group-by, strict schemas, defensive limits, and PostgreSQL percentile functions.
- Redis Query Engine cache uses workspace-aware keys, TTLs, JSON DTO serialization, and PostgreSQL fallback on Redis failure.
- Alert evaluation bypasses query cache to preserve fresh incident transitions.
- Incident transitions use database constraints and row locking to avoid duplicate active incidents.
- Notification delivery is durable, asynchronous, retryable, and idempotent by incident/channel/event.
- Audit and incident metadata use safe structured fields rather than raw request bodies.
- Service dependency impact walks upstream dependents where `source -> target` means source depends on target.

## Performance / Verification

These are local measurements from the repository validation notes, not production traffic guarantees.

- Backend tests: `161 passed`.
- Frontend tests: `57 passed`.
- Bundle analysis: `752,320` raw JS bytes and `221,455` gzip bytes across aggregate `.next/static/chunks` assets.
- Local API-key ingestion: about `7.5k events/s` for a 10,000-event batch on the measured Docker setup.
- Local Query Engine samples: about `11 ms` for a p95 latency query with a service filter, and about `62 ms` for grouped p95 by service.
- Dashboard retention controls include `10,000`, `50,000`, and `100,000` point capacity presets; the live path uses a fixed-capacity store and custom rendering rather than a charting library.

See [PERFORMANCE.md](PERFORMANCE.md) for methodology, caveats, and additional local measurements.

## Tech Stack

Frontend:
- Next.js App Router
- React
- TypeScript
- Canvas 2D and SVG
- Web Workers
- Vitest, ESLint

Backend:
- FastAPI
- Pydantic v2
- SQLAlchemy 2
- Alembic
- PyJWT
- Passlib/bcrypt
- Pytest

Data / messaging:
- PostgreSQL
- Redis Streams
- Redis query cache
- Celery worker and beat

Deployment:
- Vercel frontend
- Railway backend
- Railway PostgreSQL
- Railway Redis

## Local Development

Clone and install frontend dependencies:

```bash
git clone https://github.com/ayushxt25/Observa.git
cd Observa
npm install
```

Create `.env.local` for the frontend:

```bash
NEXT_PUBLIC_OBSERVA_API_URL=http://localhost:8001
```

Start backend services from the repository root:

```bash
docker compose up --build
```

The Compose backend runs Alembic before Uvicorn startup. If running the backend manually from `backend/`, run migrations yourself:

```bash
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
alembic upgrade head
uvicorn app.main:app --reload
```

Start the frontend:

```bash
npm run dev
```

Expected local URLs:

- Frontend: [http://localhost:3000](http://localhost:3000)
- Dashboard: [http://localhost:3000/dashboard](http://localhost:3000/dashboard)
- Backend API: [http://localhost:8001](http://localhost:8001)
- Backend docs: [http://localhost:8001/docs](http://localhost:8001/docs)

To generate telemetry against a running backend, create a workspace API key in the UI and pass it to the generator:

```bash
cd backend
python -m scripts.generate_telemetry --url http://localhost:8001 --api-key <api-key> --count 10000 --batch-size 500 --seed 42
```

## Production Deployment

Current deployment:

- Frontend: Vercel
- Backend: Railway
- PostgreSQL: Railway
- Redis: Railway

The frontend expects `NEXT_PUBLIC_OBSERVA_API_URL` to be the backend base URL only, without `/api/v1`.

```bash
NEXT_PUBLIC_OBSERVA_API_URL=https://observa-production-d905.up.railway.app
```

The backend Docker startup runs:

```bash
alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
```

Production backend settings must include explicit frontend CORS origins, secure cookies, strong JWT/notification secrets, and Railway PostgreSQL/Redis URLs. Secrets are not documented in this repository.

## API

Live Swagger docs are available at:

[https://observa-production-d905.up.railway.app/docs](https://observa-production-d905.up.railway.app/docs)

Major API groups:

- `/api/v1/auth`
- `/api/v1/workspaces`
- `/api/v1/telemetry`
- `/api/v1/query`
- `/api/v1/dashboards`
- `/api/v1/alerts`
- `/api/v1/incidents`
- `/api/v1/services`
- `/api/v1/notification-channels`
- `/api/v1/notification-deliveries`
- `/api/v1/audit-events`

`GET /api/v1/metrics/query` remains as a deprecated compatibility endpoint. Current historical dashboard widgets use `POST /api/v1/query`.

## Testing

Frontend:

```bash
npm run lint
npm run typecheck
npm run test
npm run build
```

Backend:

```bash
cd backend
python -m pytest
python -m alembic heads
python -m alembic current
```

Docker:

```bash
docker compose config
docker compose ps
```

CI runs frontend lint/typecheck/test/build and backend Alembic/Pytest against PostgreSQL and Redis services.

## Repository Structure

```text
app/                    Next.js App Router pages and route handlers
components/             Dashboard, charts, controls, providers, UI
hooks/                  Frontend hooks
lib/                    Telemetry store, API clients, query mapping, rendering utilities
workers/                Web Worker aggregation path
tests/                  Vitest frontend tests
backend/
  app/                  FastAPI application
  alembic/              Database migrations
  scripts/              Telemetry generator
  tests/                Pytest backend tests
docs/                   API and architecture documentation
public/screenshots/     README screenshots
```

## Release

Current release: `v1.0.0`.

See [CHANGELOG.md](CHANGELOG.md) for the release summary and limitations.

## Known Limitations

- No OAuth/social login.
- No OpenTelemetry Collector or distributed tracing integration.
- No Slack/PagerDuty/Teams notification integrations.
- No billing, SSO, SCIM, or enterprise organization hierarchy.
- Service dependencies are manually configured; Observa does not infer dependency graphs from traces.
- Notification delivery is at-least-once; webhook consumers should deduplicate using the delivery identifier.
- Redis Query Engine cache does not include a distributed stampede lock.
- `GET /api/v1/metrics/query` is retained for compatibility.
- The deployment is a portfolio/demo-scale production deployment, not a claim of large-scale production traffic.

## Additional Documentation

- [PERFORMANCE.md](PERFORMANCE.md)
- [backend/README.md](backend/README.md)
- [docs/telemetry-api.md](docs/telemetry-api.md)
- [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md)
