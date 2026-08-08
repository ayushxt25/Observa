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

Migration `0001` creates `telemetry_events` and indexes common time/service/region query paths. Migration `0002` creates `dashboards` and `dashboard_widgets` with cascade delete and widget-order indexes.

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
- `GET /api/v1/dashboards`
- `POST /api/v1/dashboards`
- `GET /api/v1/dashboards/{id}`
- `PATCH /api/v1/dashboards/{id}`
- `DELETE /api/v1/dashboards/{id}`
- `POST /api/v1/dashboards/{id}/widgets`
- `PATCH /api/v1/dashboards/{id}/widgets/{widget_id}`
- `DELETE /api/v1/dashboards/{id}/widgets/{widget_id}`

The API uses camelCase JSON to align with the frontend domain, while Python models use snake_case internally.
Live SSE reads from Redis Streams; historical HTTP reads remain PostgreSQL-backed.
Dashboard endpoints persist view configuration only; they do not store telemetry samples or create live streams.

## Tests

```powershell
pytest
```

Tests use dependency overrides and pure validation/service checks so they do not require a production database.
