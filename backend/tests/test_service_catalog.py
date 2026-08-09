import asyncio
from collections.abc import Generator
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_auth_repository
from app.api.v1.routes.services import get_catalog_repository
from app.db.base import Base
from app.main import app
from app.models.alerts import AlertRuleModel, IncidentModel
from app.models.services import ServiceCatalogModel, ServiceDependencyModel
from app.models.telemetry import TelemetryEventModel
from app.repositories.auth import AuthRepository
from app.repositories.services import ServiceCatalogRepository
from app.repositories.telemetry import TelemetryRepository
from app.schemas.telemetry import TelemetryEventIn
from app.services.ingestion import IngestionService
from tests.auth_helpers import authenticate_test_client


class FakeBroker:
    async def publish(self, workspace_id: str, events: list[TelemetryEventIn]) -> None:
        self.workspace_id = workspace_id
        self.events = events


def telemetry_event(event_id: str, service: str, timestamp: datetime | None = None, latency: float = 100, error_rate: float = 0) -> TelemetryEventIn:
    return TelemetryEventIn(
        id=event_id,
        timestamp=timestamp or datetime.now(timezone.utc),
        service=service,
        region="us-east",
        latency=latency,
        throughput=200,
        cpu_usage=30,
        memory_usage=40,
        error_rate=error_rate,
        payload_size=100,
        status="healthy",
    )


def test_ingestion_auto_discovers_services_and_updates_last_seen() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    first_seen = datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc)
    later = first_seen + timedelta(minutes=2)
    with SessionLocal() as db:
        service = IngestionService(TelemetryRepository(db), FakeBroker())
        response = asyncio.run(service.ingest("workspace-a", [
            telemetry_event("e1", "api-gateway", first_seen),
            telemetry_event("e2", "api-gateway", later),
            telemetry_event("e3", "auth-service", first_seen),
        ]))
        assert response.accepted_count == 3
        rows = {row.name: row for row in db.scalars(select(ServiceCatalogModel)).all()}
        assert set(rows) == {"api-gateway", "auth-service"}
        assert rows["api-gateway"].last_seen_at == later.replace(tzinfo=None)

        duplicate = asyncio.run(service.ingest("workspace-a", [telemetry_event("e1", "api-gateway", later + timedelta(minutes=5))]))
        assert duplicate.accepted_count == 0
        assert db.scalars(select(ServiceCatalogModel).where(ServiceCatalogModel.name == "api-gateway")).one().last_seen_at == later.replace(tzinfo=None)


def _service_payload(name: str = "api-gateway") -> dict[str, object]:
    return {"name": name, "displayName": "Gateway", "environment": "prod", "tags": ["edge", "prod"]}


@pytest.fixture
def service_client() -> Generator[tuple[TestClient, Session, str], None, None]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, expire_on_commit=False)()
    app.dependency_overrides[get_auth_repository] = lambda: AuthRepository(db)
    app.dependency_overrides[get_catalog_repository] = lambda: ServiceCatalogRepository(db)
    try:
        with TestClient(app) as client:
            workspace_id = authenticate_test_client(client, db)
            yield client, db, workspace_id
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_service_catalog_crud_canonical_name_and_delete_preserves_telemetry(service_client: tuple[TestClient, Session, str]) -> None:
    client, db, workspace_id = service_client
    created = client.post("/api/v1/services/catalog", json=_service_payload())
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["health"] == "unknown"
    assert body["tags"] == ["edge", "prod"]
    assert client.post("/api/v1/services/catalog", json=_service_payload()).status_code == 422

    patch = client.patch(f"/api/v1/services/catalog/{body['id']}", json={"name": "worker", "displayName": "New"})
    assert patch.status_code == 422
    updated = client.patch(f"/api/v1/services/catalog/{body['id']}", json={"displayName": "Public gateway", "environment": "production"})
    assert updated.status_code == 200
    assert updated.json()["name"] == "api-gateway"
    assert updated.json()["displayName"] == "Public gateway"

    db.add(TelemetryEventModel(id="event-1", workspace_id=workspace_id, timestamp=datetime.now(timezone.utc), service="api-gateway", region="us-east", latency=1, throughput=1, cpu_usage=1, memory_usage=1, error_rate=0, payload_size=1, status="healthy"))
    db.commit()
    assert client.delete(f"/api/v1/services/catalog/{body['id']}").status_code == 204
    assert db.scalars(select(TelemetryEventModel).where(TelemetryEventModel.service == "api-gateway")).first() is not None


def test_dependencies_validate_workspace_source_target_and_duplicates(service_client: tuple[TestClient, Session, str]) -> None:
    client, db, workspace_id = service_client
    source = client.post("/api/v1/services/catalog", json=_service_payload("api-gateway")).json()
    target = client.post("/api/v1/services/catalog", json=_service_payload("auth-service")).json()

    created = client.post("/api/v1/service-dependencies", json={"sourceServiceId": source["id"], "targetServiceId": target["id"], "dependencyType": "http"})
    assert created.status_code == 201, created.text
    assert created.json()["sourceServiceName"] == "api-gateway"
    assert client.post("/api/v1/service-dependencies", json={"sourceServiceId": source["id"], "targetServiceId": target["id"], "dependencyType": "http"}).status_code == 422
    assert client.post("/api/v1/service-dependencies", json={"sourceServiceId": source["id"], "targetServiceId": source["id"], "dependencyType": "http"}).status_code == 422

    other = ServiceCatalogModel(workspace_id="other-workspace", name="worker", tags_json="[]")
    db.add(other)
    db.commit()
    cross = client.post("/api/v1/service-dependencies", json={"sourceServiceId": source["id"], "targetServiceId": other.id, "dependencyType": "queue"})
    assert cross.status_code == 422
    assert db.scalars(select(ServiceDependencyModel).where(ServiceDependencyModel.workspace_id == workspace_id)).first() is not None


def test_service_summary_health_uses_recent_telemetry_and_active_incidents(service_client: tuple[TestClient, Session, str]) -> None:
    client, db, workspace_id = service_client
    service = client.post("/api/v1/services/catalog", json=_service_payload("auth-service")).json()
    now = datetime.now(timezone.utc)
    db.add_all([
        TelemetryEventModel(id="event-1", workspace_id=workspace_id, timestamp=now, service="auth-service", region="us-east", latency=700, throughput=20, cpu_usage=1, memory_usage=1, error_rate=8, payload_size=1, status="critical"),
        AlertRuleModel(id="rule-1", workspace_id=workspace_id, name="Auth latency", metric="latency", service="auth-service", region=None, aggregation="avg", bucket="1m", evaluation_window_seconds=60, operator=">=", threshold=100, evaluation_interval_seconds=60, cooldown_seconds=0, enabled=True, state="firing"),
        IncidentModel(id="incident-1", workspace_id=workspace_id, alert_rule_id="rule-1", status="firing", opened_at=now, triggering_value=700, threshold=100, message="firing"),
    ])
    db.commit()
    summary = client.get(f"/api/v1/services/catalog/{service['id']}/summary")
    assert summary.status_code == 200, summary.text
    body = summary.json()
    assert body["health"] == "critical"
    assert body["recentEventCount"] == 1
    assert body["activeIncidentCount"] == 1


def test_viewer_cannot_mutate_service_catalog() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, expire_on_commit=False)()
    app.dependency_overrides[get_auth_repository] = lambda: AuthRepository(db)
    app.dependency_overrides[get_catalog_repository] = lambda: ServiceCatalogRepository(db)
    try:
        with TestClient(app) as client:
            authenticate_test_client(client, db, role="viewer")
            assert client.get("/api/v1/services/catalog").status_code == 200
            assert client.post("/api/v1/services/catalog", json=_service_payload()).status_code == 403
    finally:
        app.dependency_overrides.clear()
        db.close()
