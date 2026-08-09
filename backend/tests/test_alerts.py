from collections.abc import Generator
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1.routes.alerts import get_alert_evaluator, get_alert_repository, get_notification_repository
from app.api.deps import get_auth_repository
from app.db.base import Base
from app.main import app
from app.models.alerts import IncidentModel
from app.models.auth import WorkspaceModel
from app.models.telemetry import TelemetryEventModel
from app.repositories.alerts import AlertRepository
from app.repositories.auth import AuthRepository
from app.repositories.notifications import NotificationRepository
from app.services.alerts import AlertEvaluationService, compare_value
from tests.auth_helpers import authenticate_test_client


@pytest.fixture
def alert_db() -> Generator[Session, None, None]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session_local = sessionmaker(bind=engine, expire_on_commit=False)
    db = session_local()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def alert_client(alert_db: Session) -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_alert_repository] = lambda: AlertRepository(alert_db)
    app.dependency_overrides[get_alert_evaluator] = lambda: AlertEvaluationService(alert_db)
    app.dependency_overrides[get_notification_repository] = lambda: NotificationRepository(alert_db)
    app.dependency_overrides[get_auth_repository] = lambda: AuthRepository(alert_db)
    with TestClient(app) as client:
        authenticate_test_client(client, alert_db)
        yield client
    app.dependency_overrides.clear()


def payload(threshold: float = 1000, enabled: bool = True) -> dict[str, object]:
    return {
        "name": "High latency",
        "metric": "latency",
        "aggregation": "avg",
        "bucket": "raw",
        "evaluationWindowSeconds": 300,
        "operator": ">=",
        "threshold": threshold,
        "evaluationIntervalSeconds": 60,
        "cooldownSeconds": 300,
        "enabled": enabled,
    }


def insert_point(db: Session, latency: float) -> None:
    now = datetime.now(timezone.utc)
    workspace_id = db.scalars(select(WorkspaceModel.id)).first()
    assert workspace_id is not None
    db.add(TelemetryEventModel(
        id=f"alert-test-{latency}-{now.timestamp()}",
        workspace_id=workspace_id,
        timestamp=now,
        service="api-gateway",
        region="us-east",
        latency=latency,
        throughput=100,
        cpu_usage=10,
        memory_usage=20,
        error_rate=0,
        payload_size=100,
        status="healthy",
    ))
    db.commit()


def test_alert_crud_and_strict_validation(alert_client: TestClient) -> None:
    created = alert_client.post("/api/v1/alerts", json=payload()).json()
    assert created["state"] == "normal"
    assert alert_client.get("/api/v1/alerts").json()["alerts"][0]["id"] == created["id"]
    assert alert_client.patch(f"/api/v1/alerts/{created['id']}", json={"name": "Renamed", "enabled": False}).json()["enabled"] is False
    assert alert_client.post("/api/v1/alerts", json={**payload(), "operator": "!="}).status_code == 422
    assert alert_client.post("/api/v1/alerts", json={**payload(), "threshold": "NaN"}).status_code == 422
    assert alert_client.post("/api/v1/alerts", json={**payload(), "evaluationIntervalSeconds": 1}).status_code == 422
    assert alert_client.patch(f"/api/v1/alerts/{created['id']}", json={"unknown": True}).status_code == 422
    assert alert_client.patch(f"/api/v1/alerts/{created['id']}", json={"bucket": "1h"}).status_code == 422
    assert alert_client.delete(f"/api/v1/alerts/{created['id']}").status_code == 204
    assert alert_client.get(f"/api/v1/alerts/{created['id']}").status_code == 404


def test_evaluation_transitions_and_incident_dedupe(alert_client: TestClient, alert_db: Session) -> None:
    insert_point(alert_db, 150)
    rule = alert_client.post("/api/v1/alerts", json=payload(threshold=100)).json()
    first = alert_client.post(f"/api/v1/alerts/{rule['id']}/evaluate").json()
    assert first["triggered"] is True
    assert first["alert"]["state"] == "firing"
    second = alert_client.post(f"/api/v1/alerts/{rule['id']}/evaluate").json()
    assert second["incidentId"] == first["incidentId"]
    assert len(alert_db.scalars(select(IncidentModel).where(IncidentModel.status == "firing")).all()) == 1

    alert_client.patch(f"/api/v1/alerts/{rule['id']}", json={"threshold": 1000})
    resolved = alert_client.post(f"/api/v1/alerts/{rule['id']}/evaluate").json()
    assert resolved["triggered"] is False
    assert resolved["alert"]["state"] == "normal"
    assert alert_client.get("/api/v1/incidents?status=resolved").json()["incidents"][0]["status"] == "resolved"
    assert alert_client.delete(f"/api/v1/alerts/{rule['id']}").status_code == 409


def test_cooldown_and_disabled_due_scan(alert_client: TestClient, alert_db: Session) -> None:
    insert_point(alert_db, 200)
    rule = alert_client.post("/api/v1/alerts", json=payload(threshold=100)).json()
    alert_client.post(f"/api/v1/alerts/{rule['id']}/evaluate")
    alert_client.patch(f"/api/v1/alerts/{rule['id']}", json={"threshold": 1000})
    alert_client.post(f"/api/v1/alerts/{rule['id']}/evaluate")
    alert_client.patch(f"/api/v1/alerts/{rule['id']}", json={"threshold": 100})
    reopened = alert_client.post(f"/api/v1/alerts/{rule['id']}/evaluate").json()
    assert reopened["alert"]["state"] == "firing"
    assert reopened["incidentId"] is None

    disabled = alert_client.post("/api/v1/alerts", json={**payload(threshold=1), "enabled": False}).json()
    due_enabled = alert_client.post("/api/v1/alerts", json={**payload(threshold=999), "name": "Due enabled"}).json()
    future = alert_client.post("/api/v1/alerts", json={**payload(threshold=999), "name": "Not due yet"}).json()
    future_rule = AlertRepository(alert_db).get_rule(future["id"])
    assert future_rule is not None
    future_rule.last_evaluated_at = datetime.now(timezone.utc)
    alert_db.commit()
    due_count = AlertEvaluationService(alert_db).evaluate_due_rules()
    assert due_count >= 1
    assert alert_client.get(f"/api/v1/alerts/{due_enabled['id']}").json()["lastEvaluatedAt"] is not None
    assert alert_client.get(f"/api/v1/alerts/{future['id']}").json()["lastEvaluatedAt"] is not None
    assert alert_client.get(f"/api/v1/alerts/{disabled['id']}").json()["lastEvaluatedAt"] is None


def test_no_data_evaluation_does_not_fire(alert_client: TestClient) -> None:
    rule = alert_client.post("/api/v1/alerts", json=payload(threshold=1)).json()
    evaluated = alert_client.post(f"/api/v1/alerts/{rule['id']}/evaluate").json()
    assert evaluated["triggered"] is False
    assert evaluated["value"] is None
    assert evaluated["alert"]["state"] == "normal"
    assert evaluated["incidentId"] is None
    assert alert_client.get("/api/v1/incidents").json()["incidents"] == []


def test_disabled_rule_after_dispatch_is_skipped(alert_client: TestClient, alert_db: Session) -> None:
    insert_point(alert_db, 300)
    rule = alert_client.post("/api/v1/alerts", json=payload(threshold=1)).json()
    alert_client.patch(f"/api/v1/alerts/{rule['id']}", json={"enabled": False})
    skipped = AlertEvaluationService(alert_db).evaluate_rule(rule["id"])
    assert skipped.triggered is False
    assert skipped.value is None
    assert alert_client.get(f"/api/v1/alerts/{rule['id']}").json()["lastEvaluatedAt"] is None


def test_due_rule_interval_selection(alert_client: TestClient, alert_db: Session) -> None:
    stale = alert_client.post("/api/v1/alerts", json={**payload(), "name": "Stale", "evaluationIntervalSeconds": 30}).json()
    fresh = alert_client.post("/api/v1/alerts", json={**payload(), "name": "Fresh", "evaluationIntervalSeconds": 30}).json()
    repo = AlertRepository(alert_db)
    stale_rule = repo.get_rule(stale["id"])
    fresh_rule = repo.get_rule(fresh["id"])
    assert stale_rule is not None and fresh_rule is not None
    now = datetime.now(timezone.utc)
    stale_rule.last_evaluated_at = now - timedelta(seconds=31)
    fresh_rule.last_evaluated_at = now - timedelta(seconds=10)
    alert_db.commit()
    due_ids = {rule.id for rule in repo.due_rules(now)}
    assert stale["id"] in due_ids
    assert fresh["id"] not in due_ids


def test_incident_filters_and_helpers(alert_client: TestClient, alert_db: Session) -> None:
    assert compare_value(2, ">", 1)
    assert compare_value(2, ">=", 2)
    assert compare_value(1, "<", 2)
    assert compare_value(2, "<=", 2)
    insert_point(alert_db, 300)
    rule = alert_client.post("/api/v1/alerts", json={**payload(threshold=10), "service": "api-gateway"}).json()
    incident_id = alert_client.post(f"/api/v1/alerts/{rule['id']}/evaluate").json()["incidentId"]
    assert alert_client.get(f"/api/v1/incidents/{incident_id}").json()["ruleName"] == "High latency"
    assert len(alert_client.get("/api/v1/incidents?service=api-gateway").json()["incidents"]) == 1
    assert len(alert_client.get(f"/api/v1/incidents?alert_rule_id={rule['id']}").json()["incidents"]) == 1
