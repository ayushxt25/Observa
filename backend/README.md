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
```

## Docker Startup

From the repository root:

```powershell
docker compose up --build
```

The backend is exposed at `http://localhost:8000`. API documentation is available at `http://localhost:8000/docs`.

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

The initial migration creates `telemetry_events` and indexes common time/service/region query paths.

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
- `GET /api/v1/metrics/query`
- `GET /api/v1/services`

The API uses camelCase JSON to align with the frontend domain, while Python models use snake_case internally.

## Tests

```powershell
pytest
```

Tests use dependency overrides and pure validation/service checks so they do not require a production database.
