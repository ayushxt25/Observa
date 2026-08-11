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
from app.query.engine import TelemetryQueryEngine
from app.query.schemas import QueryFilters, TelemetryQueryRequest
from app.repositories.alerts import AlertRepository
from app.repositories.auth import AuthRepository
from app.repositories.notifications import NotificationRepository
from app.schemas.alerts import AlertRuleCreate
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
    insert_event(db, workspace_id, f"alert-test-{latency}-{now.timestamp()}", now, latency=latency)


def insert_event(
    db: Session,
    workspace_id: str,
    event_id: str,
    timestamp: datetime,
    *,
    service: str = "api-gateway",
    region: str = "us-east",
    latency: float = 100,
    throughput: float = 100,
    cpu_usage: float = 10,
    memory_usage: float = 20,
    error_rate: float = 0,
    payload_size: float = 100,
) -> None:
    db.add(TelemetryEventModel(
        id=event_id,
        workspace_id=workspace_id,
        timestamp=timestamp,
        service=service,
        region=region,
        latency=latency,
        throughput=throughput,
        cpu_usage=cpu_usage,
        memory_usage=memory_usage,
        error_rate=error_rate,
        payload_size=payload_size,
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


def test_no_data_preserves_existing_resolution_behavior(alert_client: TestClient, alert_db: Session) -> None:
    insert_point(alert_db, 300)
    rule = alert_client.post("/api/v1/alerts", json=payload(threshold=100)).json()
    first = alert_client.post(f"/api/v1/alerts/{rule['id']}/evaluate").json()
    assert first["alert"]["state"] == "firing"
    alert_db.query(TelemetryEventModel).delete()
    alert_db.commit()

    evaluated = alert_client.post(f"/api/v1/alerts/{rule['id']}/evaluate").json()
    assert evaluated["value"] is None
    assert evaluated["triggered"] is False
    assert evaluated["alert"]["state"] == "normal"
    assert alert_client.get("/api/v1/incidents?status=resolved").json()["incidents"][0]["id"] == first["incidentId"]


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


@pytest.mark.parametrize(
    ("metric", "query_metric", "aggregation", "expected"),
    [
        ("latency", "latency", "avg", 200),
        ("latency", "latency", "min", 100),
        ("latency", "latency", "max", 300),
        ("latency", "latency", "sum", 600),
        ("latency", "latency", "count", 3),
        ("throughput", "throughput", "avg", 20),
        ("cpuUsage", "cpu_usage", "max", 30),
        ("memoryUsage", "memory_usage", "min", 20),
        ("errorRate", "error_rate", "avg", 5),
        ("payloadSize", "payload_size", "sum", 6000),
    ],
)
def test_alert_value_matches_query_engine_metrics_and_aggregations(
    alert_client: TestClient,
    alert_db: Session,
    metric: str,
    query_metric: str,
    aggregation: str,
    expected: float,
) -> None:
    workspace_id = alert_db.scalars(select(WorkspaceModel.id)).first()
    assert workspace_id is not None
    now = datetime.now(timezone.utc)
    for index, value in enumerate([1, 2, 3], start=1):
        insert_event(
            alert_db,
            workspace_id,
            f"metric-{metric}-{aggregation}-{index}",
            now - timedelta(seconds=60 - index),
            latency=value * 100,
            throughput=value * 10,
            cpu_usage=value * 10,
            memory_usage=value * 20,
            error_rate=value * 2.5,
            payload_size=value * 1000,
        )
    rule_payload = {**payload(threshold=999999), "metric": metric, "aggregation": aggregation, "bucket": "raw", "evaluationWindowSeconds": 300}
    rule = alert_client.post("/api/v1/alerts", json=rule_payload).json()
    model = AlertRepository(alert_db).get_rule(rule["id"])
    assert model is not None

    value = AlertEvaluationService(alert_db)._read_value(model, now)
    direct = TelemetryQueryEngine(alert_db).execute(
        workspace_id,
        TelemetryQueryRequest(
            metric=query_metric,
            aggregation=aggregation,
            start=now - timedelta(seconds=300),
            end=now,
            bucket="raw",
            filters=QueryFilters(),
        ),
    ).series[0].points[0].value
    assert value == pytest.approx(expected)
    assert value == pytest.approx(direct)


@pytest.mark.parametrize(
    ("operator", "value", "threshold", "triggered"),
    [
        (">", 5, 5, False),
        (">", 5.001, 5, True),
        (">=", 5, 5, True),
        ("<", 5, 5, False),
        ("<", 4.999, 5, True),
        ("<=", 5, 5, True),
    ],
)
def test_alert_threshold_boundaries(alert_client: TestClient, alert_db: Session, operator: str, value: float, threshold: float, triggered: bool) -> None:
    workspace_id = alert_db.scalars(select(WorkspaceModel.id)).first()
    assert workspace_id is not None
    now = datetime.now(timezone.utc)
    insert_event(alert_db, workspace_id, f"boundary-{operator}-{value}", now, latency=value)
    rule = alert_client.post("/api/v1/alerts", json={**payload(threshold=threshold), "operator": operator}).json()
    evaluated = alert_client.post(f"/api/v1/alerts/{rule['id']}/evaluate").json()
    assert evaluated["triggered"] is triggered


@pytest.mark.parametrize(
    ("value", "operator", "threshold", "triggered"),
    [
        (4.999, ">=", 5, False),
        (5, ">=", 5, True),
        (5.001, ">=", 5, True),
    ],
)
def test_error_rate_alert_uses_percentage_points(alert_client: TestClient, alert_db: Session, value: float, operator: str, threshold: float, triggered: bool) -> None:
    workspace_id = alert_db.scalars(select(WorkspaceModel.id)).first()
    assert workspace_id is not None
    now = datetime.now(timezone.utc)
    insert_event(alert_db, workspace_id, f"error-rate-{value}", now, error_rate=value)
    rule = alert_client.post("/api/v1/alerts", json={**payload(threshold=threshold), "metric": "errorRate", "operator": operator}).json()
    evaluated = alert_client.post(f"/api/v1/alerts/{rule['id']}/evaluate").json()
    assert evaluated["value"] == pytest.approx(value)
    assert evaluated["triggered"] is triggered


def test_query_engine_failure_rolls_back_alert_state(alert_client: TestClient, alert_db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    insert_point(alert_db, 300)
    rule = alert_client.post("/api/v1/alerts", json=payload(threshold=100)).json()

    def fail_execute(*_args, **_kwargs):
        raise RuntimeError("query failed")

    monkeypatch.setattr(TelemetryQueryEngine, "execute", fail_execute)
    with pytest.raises(RuntimeError):
        AlertEvaluationService(alert_db).evaluate_rule(rule["id"])
    model = AlertRepository(alert_db).get_rule(rule["id"])
    assert model is not None
    assert model.state == "normal"
    assert model.last_evaluated_at is None
    assert alert_db.scalars(select(IncidentModel)).all() == []


def test_alert_query_is_workspace_scoped_for_identical_service_names(alert_db: Session) -> None:
    now = datetime.now(timezone.utc)
    workspace_a = "workspace-a"
    workspace_b = "workspace-b"
    alert_db.add(WorkspaceModel(id=workspace_a, name="Workspace A", slug="workspace-a"))
    alert_db.add(WorkspaceModel(id=workspace_b, name="Workspace B", slug="workspace-b"))
    alert_db.commit()
    insert_event(alert_db, workspace_a, "a-auth", now, service="auth-service", latency=100)
    insert_event(alert_db, workspace_b, "b-auth", now, service="auth-service", latency=1000)

    repo = AlertRepository(alert_db)
    rule_payload = AlertRuleCreate(**{**payload(threshold=500), "service": "auth-service"})
    rule_a = repo.create_rule(rule_payload, workspace_a)
    rule_b = repo.create_rule(rule_payload, workspace_b)

    evaluated_a = AlertEvaluationService(alert_db).evaluate_rule(rule_a.id, now=now + timedelta(seconds=1))
    evaluated_b = AlertEvaluationService(alert_db).evaluate_rule(rule_b.id, now=now + timedelta(seconds=1))
    assert evaluated_a.triggered is False
    assert evaluated_a.value == pytest.approx(100)
    assert evaluated_b.triggered is True
    assert evaluated_b.value == pytest.approx(1000)


def test_alert_evaluation_bypasses_public_query_cache(alert_client: TestClient, alert_db: Session) -> None:
    workspace_id = alert_db.scalars(select(WorkspaceModel.id)).first()
    assert workspace_id is not None
    now = datetime.now(timezone.utc)
    insert_event(alert_db, workspace_id, "cached-non-breach", now - timedelta(seconds=10), latency=100)
    insert_event(alert_db, workspace_id, "fresh-breach", now, latency=1000)
    rule = alert_client.post("/api/v1/alerts", json=payload(threshold=500)).json()
    service = AlertEvaluationService(alert_db)
    assert service.query_engine.cache is None
    evaluated = service.evaluate_rule(rule["id"], now=now + timedelta(seconds=1))
    assert evaluated.triggered is True
    assert evaluated.value == pytest.approx(550)
