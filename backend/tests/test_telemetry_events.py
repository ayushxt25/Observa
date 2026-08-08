from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from fastapi import status
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.v1.routes import telemetry as telemetry_routes
from app.db.base import Base
from app.main import app
from app.models.telemetry import TelemetryEventModel
from app.repositories.telemetry import TelemetryRepository
from app.schemas.metrics import MetricQueryParams


def row(event_id: str, timestamp: datetime):
    return SimpleNamespace(
        id=event_id,
        timestamp=timestamp,
        service="api-gateway",
        region="us-east",
        latency=100.0,
        throughput=200.0,
        cpu_usage=40.0,
        memory_usage=50.0,
        error_rate=0.2,
        payload_size=1024,
        status="healthy",
        created_at=timestamp,
    )


class SmallQuerySettings:
    max_ingest_batch_size = 5000
    max_query_rows = 3


def test_query_events_default_cap_and_empty_result(client, monkeypatch) -> None:
    calls: list[tuple[int, bool]] = []

    class FakeRepo:
        def __init__(self, db) -> None:
            pass

        def events(self, params, limit: int, *, latest: bool):
            calls.append((limit, latest))
            return [], False

    app.dependency_overrides[telemetry_routes.get_db] = lambda: object()
    app.dependency_overrides[telemetry_routes.get_settings] = lambda: SmallQuerySettings()
    monkeypatch.setattr(telemetry_routes, "TelemetryRepository", FakeRepo)

    response = client.get("/api/v1/telemetry")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"events": [], "limited": False}
    assert calls == [(3, True)]


def test_query_events_rejects_limit_above_effective_cap(client) -> None:
    app.dependency_overrides[telemetry_routes.get_db] = lambda: object()
    app.dependency_overrides[telemetry_routes.get_settings] = lambda: SmallQuerySettings()
    response = client.get("/api/v1/telemetry?limit=4")
    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_query_events_validates_limit(client) -> None:
    response = client.get("/api/v1/telemetry?limit=0")
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_query_events_applies_filters(client, monkeypatch) -> None:
    captured: list[MetricQueryParams] = []
    now = datetime.now(timezone.utc)

    class FakeRepo:
        def __init__(self, db) -> None:
            pass

        def events(self, params, limit: int, *, latest: bool):
            captured.append(params)
            return [row("event-1", now)], False

    app.dependency_overrides[telemetry_routes.get_db] = lambda: object()
    app.dependency_overrides[telemetry_routes.get_settings] = lambda: SmallQuerySettings()
    monkeypatch.setattr(telemetry_routes, "TelemetryRepository", FakeRepo)

    response = client.get(
        "/api/v1/telemetry"
        "?start=2026-08-07T12:00:00Z&end=2026-08-07T12:01:00Z"
        "&service=api-gateway&region=us-east&limit=2"
    )
    assert response.status_code == status.HTTP_200_OK
    assert captured[0].service == "api-gateway"
    assert captured[0].region == "us-east"
    assert captured[0].start is not None
    assert captured[0].end is not None


def test_repository_events_are_deterministically_ordered_and_filtered() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    base_time = datetime(2026, 8, 7, 12, tzinfo=timezone.utc)
    with Session() as session:
        session.add_all([
            TelemetryEventModel(id="b", timestamp=base_time, service="api-gateway", region="us-east", latency=1, throughput=1, cpu_usage=1, memory_usage=1, error_rate=0, payload_size=1, status="healthy"),
            TelemetryEventModel(id="a", timestamp=base_time, service="api-gateway", region="us-east", latency=1, throughput=1, cpu_usage=1, memory_usage=1, error_rate=0, payload_size=1, status="healthy"),
            TelemetryEventModel(id="c", timestamp=base_time + timedelta(seconds=1), service="worker", region="us-east", latency=1, throughput=1, cpu_usage=1, memory_usage=1, error_rate=0, payload_size=1, status="healthy"),
            TelemetryEventModel(id="d", timestamp=base_time + timedelta(seconds=2), service="api-gateway", region="us-west", latency=1, throughput=1, cpu_usage=1, memory_usage=1, error_rate=0, payload_size=1, status="healthy"),
        ])
        session.commit()

        repo = TelemetryRepository(session)
        rows, limited = repo.events(MetricQueryParams(service="api-gateway"), 2, latest=True)
        assert [event.id for event in rows] == ["b", "d"]
        assert limited is True

        filtered, filtered_limited = repo.events(MetricQueryParams(region="us-west"), 10, latest=False)
        assert [event.id for event in filtered] == ["d"]
        assert filtered_limited is False
