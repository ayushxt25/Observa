from datetime import datetime, timezone

from fastapi import status

from app.api.v1.routes.health import get_database_ready, get_health_broker
from app.api.v1.routes.metrics import get_metrics_service
from app.api.v1.routes.telemetry import get_ingestion_service
from app.core.config import get_settings
from app.main import app
from app.schemas.metrics import MetricQueryResponse
from app.schemas.telemetry import IngestionResponse, ServicesResponse


def event_payload(event_id: str = "event-1") -> dict[str, object]:
    return {
        "id": event_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": "api-gateway",
        "region": "us-east",
        "latency": 120.5,
        "throughput": 900.0,
        "cpuUsage": 52.0,
        "memoryUsage": 61.0,
        "errorRate": 0.4,
        "payloadSize": 2048,
        "status": "healthy",
    }


class FakeIngestionService:
    async def ingest(self, events):
        return IngestionResponse(
            accepted_count=len(events),
            rejected_count=0,
            processing_duration_ms=1.25,
        )


class FakeMetricsService:
    def query(self, params):
        return MetricQueryResponse(
            metric=params.metric,
            aggregation=params.aggregation,
            bucket=params.bucket,
            points=[],
            processing_duration_ms=0.5,
            limited=False,
        )

    def services(self):
        return ServicesResponse(services=[])


class FakeBroker:
    async def ready(self) -> bool:
        return True


def test_single_ingestion(client) -> None:
    app.dependency_overrides[get_ingestion_service] = lambda: FakeIngestionService()
    response = client.post("/api/v1/telemetry", json=event_payload())
    assert response.status_code == status.HTTP_202_ACCEPTED
    assert response.json()["acceptedCount"] == 1


def test_batch_ingestion(client) -> None:
    app.dependency_overrides[get_ingestion_service] = lambda: FakeIngestionService()
    payload = {"events": [event_payload("event-1"), event_payload("event-2")]}
    response = client.post("/api/v1/telemetry/batch", json=payload)
    assert response.status_code == status.HTTP_202_ACCEPTED
    assert response.json()["acceptedCount"] == 2


def test_max_batch_size_enforced(client) -> None:
    class SmallBatchSettings:
        max_ingest_batch_size = 2

    app.dependency_overrides[get_settings] = lambda: SmallBatchSettings()
    app.dependency_overrides[get_ingestion_service] = lambda: FakeIngestionService()
    oversized = [event_payload(f"event-{index}") for index in range(3)]
    response = client.post("/api/v1/telemetry/batch", json={"events": oversized})
    assert response.status_code == status.HTTP_413_REQUEST_ENTITY_TOO_LARGE


def test_metric_query_endpoint(client) -> None:
    app.dependency_overrides[get_metrics_service] = lambda: FakeMetricsService()
    response = client.get("/api/v1/metrics/query?metric=latency&aggregation=avg&bucket=1m")
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["metric"] == "latency"


def test_health_endpoint(client) -> None:
    response = client.get("/health")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"status": "ok"}


def test_ready_endpoint(client) -> None:
    app.dependency_overrides[get_database_ready] = lambda: True
    app.dependency_overrides[get_health_broker] = lambda: FakeBroker()
    response = client.get("/ready")
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["status"] == "ready"
