from collections.abc import AsyncIterator

from fastapi import status

from app.api.v1.routes import telemetry as telemetry_routes
from app.main import app
from app.streaming.broker import TelemetryStreamCursorError


class FakeStreamBroker:
    def __init__(self) -> None:
        self.closed = False
        self.cursors: list[str] = []

    async def latest_id(self) -> str:
        return "42-0"

    def validate_cursor(self, cursor: str) -> str:
        if cursor == "bad":
            raise TelemetryStreamCursorError("Invalid Redis stream cursor")
        return cursor

    async def read_batches(self, cursor: str, *, block_ms: int = 15_000, count: int = 10) -> AsyncIterator[tuple[str, list[dict[str, object]]]]:
        self.cursors.append(cursor)
        yield "43-0", [{
            "id": "event-1",
            "timestamp": "2026-08-07T12:00:00Z",
            "service": "api-gateway",
            "region": "us-east",
            "latency": 100,
            "throughput": 200,
            "cpuUsage": 40,
            "memoryUsage": 50,
            "errorRate": 0.2,
            "payloadSize": 1024,
            "status": "healthy",
        }]
        yield "43-0", []


def test_stream_cursor_endpoint(client) -> None:
    app.dependency_overrides[telemetry_routes.get_broker] = lambda: FakeStreamBroker()
    response = client.get("/api/v1/telemetry/stream/cursor")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"cursor": "42-0"}


def test_stream_rejects_invalid_cursor(client) -> None:
    app.dependency_overrides[telemetry_routes.get_broker] = lambda: FakeStreamBroker()
    response = client.get("/api/v1/telemetry/stream?cursor=bad")
    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_stream_headers_and_event_mapping(client) -> None:
    broker = FakeStreamBroker()
    app.dependency_overrides[telemetry_routes.get_broker] = lambda: broker
    with client.stream("GET", "/api/v1/telemetry/stream?cursor=42-0") as response:
        body = next(response.iter_text())
    assert response.status_code == status.HTTP_200_OK
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "id: 43-0" in body
    assert "event: telemetry" in body
    assert "api-gateway" in body
    assert broker.cursors == ["42-0"]


def test_stream_resume_uses_last_event_id_header(client) -> None:
    broker = FakeStreamBroker()
    app.dependency_overrides[telemetry_routes.get_broker] = lambda: broker
    with client.stream("GET", "/api/v1/telemetry/stream", headers={"Last-Event-ID": "41-0"}) as response:
        next(response.iter_text())
    assert response.status_code == status.HTTP_200_OK
    assert broker.cursors == ["41-0"]
