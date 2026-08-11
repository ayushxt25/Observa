from collections.abc import Generator
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_auth_repository
from app.api.v1.routes.alerts import get_alert_evaluator, get_alert_repository, get_notification_repository
from app.db.base import Base
from app.main import app
from app.models.alerts import AlertRuleModel, IncidentEventModel, IncidentModel
from app.models.notifications import AlertNotificationChannelModel, NotificationChannelModel, NotificationDeliveryModel
from app.models.services import ServiceCatalogModel, ServiceDependencyModel
from app.models.telemetry import TelemetryEventModel
from app.repositories.alerts import AlertRepository
from app.repositories.auth import AuthRepository
from app.repositories.notifications import NotificationRepository
from app.services.alerts import AlertEvaluationService
from app.services.incident_intelligence import IncidentImpactServiceBuilder, IncidentTimelineService
from tests.auth_helpers import authenticate_test_client


@pytest.fixture
def intelligence_client() -> Generator[tuple[TestClient, Session, str], None, None]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, expire_on_commit=False)()
    app.dependency_overrides[get_alert_repository] = lambda: AlertRepository(db)
    app.dependency_overrides[get_alert_evaluator] = lambda: AlertEvaluationService(db)
    app.dependency_overrides[get_notification_repository] = lambda: NotificationRepository(db)
    app.dependency_overrides[get_auth_repository] = lambda: AuthRepository(db)
    try:
        with TestClient(app) as client:
            workspace_id = authenticate_test_client(client, db)
            yield client, db, workspace_id
    finally:
        app.dependency_overrides.clear()
        db.close()


def _event(db: Session, workspace_id: str, event_id: str, latency: float, service: str = "auth-service") -> None:
    db.add(TelemetryEventModel(
        id=event_id,
        workspace_id=workspace_id,
        timestamp=datetime.now(timezone.utc),
        service=service,
        region="us-east",
        latency=latency,
        throughput=10,
        cpu_usage=10,
        memory_usage=20,
        error_rate=0,
        payload_size=100,
        status="healthy",
    ))
    db.commit()


def _alert_payload(threshold: float = 100) -> dict[str, object]:
    return {
        "name": "Auth latency",
        "metric": "latency",
        "aggregation": "avg",
        "bucket": "raw",
        "evaluationWindowSeconds": 300,
        "operator": ">=",
        "threshold": threshold,
        "evaluationIntervalSeconds": 60,
        "cooldownSeconds": 0,
        "enabled": True,
        "service": "auth-service",
    }


def _service(db: Session, workspace_id: str, service_id: str, name: str) -> ServiceCatalogModel:
    item = ServiceCatalogModel(id=service_id, workspace_id=workspace_id, name=name, display_name=name.title(), tags_json="[]")
    db.add(item)
    return item


def _rule_and_incident(db: Session, workspace_id: str, service: str | None = "auth-service") -> IncidentModel:
    rule = AlertRuleModel(id=f"rule-{service or 'none'}", workspace_id=workspace_id, name="Rule", metric="latency", service=service, aggregation="avg", bucket="raw", evaluation_window_seconds=60, operator=">=", threshold=1, evaluation_interval_seconds=60, cooldown_seconds=0, enabled=True, state="firing")
    incident = IncidentModel(id=f"incident-{service or 'none'}", workspace_id=workspace_id, alert_rule_id=rule.id, status="firing", opened_at=datetime.now(timezone.utc), triggering_value=2, threshold=1, message="open", alert_rule=rule)
    db.add_all([rule, incident])
    db.commit()
    return incident


def test_timeline_open_resolve_events_and_no_continued_breach_spam(intelligence_client: tuple[TestClient, Session, str]) -> None:
    client, db, workspace_id = intelligence_client
    _event(db, workspace_id, "e1", 300)
    rule = client.post("/api/v1/alerts", json=_alert_payload()).json()
    opened = client.post(f"/api/v1/alerts/{rule['id']}/evaluate").json()
    client.post(f"/api/v1/alerts/{rule['id']}/evaluate")
    client.patch(f"/api/v1/alerts/{rule['id']}", json={"threshold": 1000})
    client.post(f"/api/v1/alerts/{rule['id']}/evaluate")

    body = client.get(f"/api/v1/incidents/{opened['incidentId']}/timeline").json()
    assert [event["eventType"] for event in body["events"]] == ["incident.opened", "incident.resolved"]
    assert body["events"][0]["metadata"]["observedValue"] == pytest.approx(300)
    assert db.scalar(select(func.count(IncidentEventModel.id)).where(IncidentEventModel.event_type == "incident.opened")) == 1


def test_timeline_metadata_is_sanitized_and_bounded(intelligence_client: tuple[TestClient, Session, str]) -> None:
    client, db, workspace_id = intelligence_client
    rule = AlertRuleModel(id="rule-1", workspace_id=workspace_id, name="Rule", metric="latency", aggregation="avg", bucket="raw", evaluation_window_seconds=60, operator=">=", threshold=1, evaluation_interval_seconds=60, cooldown_seconds=0, enabled=True, state="normal")
    incident = IncidentModel(id="incident-1", workspace_id=workspace_id, alert_rule_id="rule-1", status="firing", opened_at=datetime.now(timezone.utc), triggering_value=2, threshold=1, message="open", alert_rule=rule)
    db.add_all([rule, incident])
    db.commit()
    IncidentTimelineService(db).record(workspace_id=workspace_id, incident_id=incident.id, event_type="incident.opened", title="Unsafe", occurred_at=incident.opened_at, dedupe_key="unsafe", metadata={"webhookSecret": "secret-value", "nested": [{"apiKey": "raw"}]})
    db.commit()

    body = client.get(f"/api/v1/incidents/{incident.id}/timeline?limit=1").json()
    assert body["events"][0]["metadata"]["webhookSecret"] == "[REDACTED]"
    assert body["events"][0]["metadata"]["nested"][0]["apiKey"] == "[REDACTED]"
    assert len(body["events"]) == 1


def test_notification_summary_and_derived_timeline_events(intelligence_client: tuple[TestClient, Session, str]) -> None:
    client, db, workspace_id = intelligence_client
    rule = AlertRuleModel(id="rule-1", workspace_id=workspace_id, name="Rule", metric="latency", aggregation="avg", bucket="raw", evaluation_window_seconds=60, operator=">=", threshold=1, evaluation_interval_seconds=60, cooldown_seconds=0, enabled=True, state="normal")
    incident = IncidentModel(id="incident-1", workspace_id=workspace_id, alert_rule_id="rule-1", status="firing", opened_at=datetime.now(timezone.utc), triggering_value=2, threshold=1, message="open", alert_rule=rule)
    delivered = NotificationDeliveryModel(id="delivery-1", workspace_id=workspace_id, alert_rule_id=rule.id, incident_id=incident.id, channel_id=None, channel_name="Ops", channel_type="webhook", channel_config_json="{}", event_type="firing", status="delivered", attempt_count=1, delivered_at=incident.opened_at + timedelta(seconds=2))
    failed = NotificationDeliveryModel(id="delivery-2", workspace_id=workspace_id, alert_rule_id=rule.id, incident_id=incident.id, channel_id=None, channel_name="Email", channel_type="email", channel_config_json="{}", event_type="firing", status="failed", attempt_count=2, last_attempt_at=incident.opened_at + timedelta(seconds=3), error_summary="failed")
    db.add_all([rule, incident, delivered, failed])
    db.commit()

    summary = client.get(f"/api/v1/incidents/{incident.id}/notifications/summary").json()["summary"]
    assert summary == {"pending": 0, "delivering": 0, "delivered": 1, "failed": 1}
    event_types = [event["eventType"] for event in client.get(f"/api/v1/incidents/{incident.id}/timeline").json()["events"]]
    assert "notification.delivered" in event_types
    assert "notification.failed" in event_types


def test_impact_chain_cycle_multiple_paths_and_minimum_depth(intelligence_client: tuple[TestClient, Session, str]) -> None:
    _client, db, workspace_id = intelligence_client
    frontend = _service(db, workspace_id, "frontend", "frontend")
    gateway = _service(db, workspace_id, "gateway", "api-gateway")
    auth = _service(db, workspace_id, "auth", "auth-service")
    user_db = _service(db, workspace_id, "db", "user-db")
    worker = _service(db, workspace_id, "worker", "worker")
    db.add_all([
        ServiceDependencyModel(id="d1", workspace_id=workspace_id, source_service=frontend, target_service=gateway, dependency_type="http"),
        ServiceDependencyModel(id="d2", workspace_id=workspace_id, source_service=gateway, target_service=auth, dependency_type="http"),
        ServiceDependencyModel(id="d3", workspace_id=workspace_id, source_service=auth, target_service=user_db, dependency_type="database"),
        ServiceDependencyModel(id="d4", workspace_id=workspace_id, source_service=worker, target_service=auth, dependency_type="queue"),
        ServiceDependencyModel(id="d5", workspace_id=workspace_id, source_service=user_db, target_service=frontend, dependency_type="unknown"),
    ])
    rule = AlertRuleModel(id="rule-1", workspace_id=workspace_id, name="DB", metric="latency", service="user-db", aggregation="avg", bucket="raw", evaluation_window_seconds=60, operator=">=", threshold=1, evaluation_interval_seconds=60, cooldown_seconds=0, enabled=True, state="firing")
    incident = IncidentModel(id="incident-1", workspace_id=workspace_id, alert_rule_id="rule-1", status="firing", opened_at=datetime.now(timezone.utc), triggering_value=2, threshold=1, message="open", alert_rule=rule)
    db.add_all([rule, incident])
    db.commit()

    impact = IncidentImpactServiceBuilder(db).impact(incident)
    depths = {item.name: item.depth for item in impact.affected_services}
    assert depths == {"user-db": 0, "auth-service": 1, "api-gateway": 2, "worker": 2, "frontend": 3}
    assert impact.max_depth == 3
    assert len(impact.affected_services) == 5


def test_dependency_direction_and_reverse_blast_radius_are_explicit(intelligence_client: tuple[TestClient, Session, str]) -> None:
    _client, db, workspace_id = intelligence_client
    frontend = _service(db, workspace_id, "frontend", "frontend")
    gateway = _service(db, workspace_id, "gateway", "api-gateway")
    auth = _service(db, workspace_id, "auth", "auth-service")
    user_db = _service(db, workspace_id, "db", "user-db")
    db.add_all([
        ServiceDependencyModel(id="edge-frontend-gateway", workspace_id=workspace_id, source_service=frontend, target_service=gateway, dependency_type="http"),
        ServiceDependencyModel(id="edge-gateway-auth", workspace_id=workspace_id, source_service=gateway, target_service=auth, dependency_type="http"),
        ServiceDependencyModel(id="edge-auth-db", workspace_id=workspace_id, source_service=auth, target_service=user_db, dependency_type="database"),
    ])
    incident = _rule_and_incident(db, workspace_id, "user-db")
    stored_edges = {(edge.source_service.name, edge.target_service.name) for edge in db.scalars(select(ServiceDependencyModel).where(ServiceDependencyModel.workspace_id == workspace_id)).all()}
    assert stored_edges == {("frontend", "api-gateway"), ("api-gateway", "auth-service"), ("auth-service", "user-db")}
    assert {item.name: item.depth for item in IncidentImpactServiceBuilder(db).impact(incident).affected_services} == {"user-db": 0, "auth-service": 1, "api-gateway": 2, "frontend": 3}


def test_direct_transitive_multiple_paths_minimum_depth(intelligence_client: tuple[TestClient, Session, str]) -> None:
    _client, db, workspace_id = intelligence_client
    a = _service(db, workspace_id, "a", "A")
    b = _service(db, workspace_id, "b", "B")
    c = _service(db, workspace_id, "c", "C")
    d = _service(db, workspace_id, "d", "D")
    db.add_all([
        ServiceDependencyModel(id="a-c", workspace_id=workspace_id, source_service=a, target_service=c, dependency_type="http"),
        ServiceDependencyModel(id="b-c", workspace_id=workspace_id, source_service=b, target_service=c, dependency_type="http"),
        ServiceDependencyModel(id="d-a", workspace_id=workspace_id, source_service=d, target_service=a, dependency_type="http"),
        ServiceDependencyModel(id="d-b", workspace_id=workspace_id, source_service=d, target_service=b, dependency_type="http"),
    ])
    impact = IncidentImpactServiceBuilder(db).impact(_rule_and_incident(db, workspace_id, "C"))
    assert {item.name: item.depth for item in impact.affected_services} == {"C": 0, "A": 1, "B": 1, "D": 2}
    assert [item.name for item in impact.affected_services].count("D") == 1


def test_cycle_reverse_dependents_no_root_duplication(intelligence_client: tuple[TestClient, Session, str]) -> None:
    _client, db, workspace_id = intelligence_client
    a = _service(db, workspace_id, "a", "A")
    b = _service(db, workspace_id, "b", "B")
    c = _service(db, workspace_id, "c", "C")
    db.add_all([
        ServiceDependencyModel(id="a-b", workspace_id=workspace_id, source_service=a, target_service=b, dependency_type="http"),
        ServiceDependencyModel(id="b-c", workspace_id=workspace_id, source_service=b, target_service=c, dependency_type="http"),
        ServiceDependencyModel(id="c-a", workspace_id=workspace_id, source_service=c, target_service=a, dependency_type="http"),
    ])
    names = [(item.name, item.depth) for item in IncidentImpactServiceBuilder(db).impact(_rule_and_incident(db, workspace_id, "C")).affected_services]
    assert names == [("C", 0), ("B", 1), ("A", 2)]


def test_impact_api_is_workspace_scoped_and_handles_missing_root(intelligence_client: tuple[TestClient, Session, str]) -> None:
    client, db, workspace_id = intelligence_client
    _service(db, workspace_id, "a-auth", "auth-service")
    _service(db, "other-workspace", "b-billing", "billing-service")
    rule = AlertRuleModel(id="rule-1", workspace_id=workspace_id, name="Missing", metric="latency", service="missing-service", aggregation="avg", bucket="raw", evaluation_window_seconds=60, operator=">=", threshold=1, evaluation_interval_seconds=60, cooldown_seconds=0, enabled=True, state="firing")
    incident = IncidentModel(id="incident-1", workspace_id=workspace_id, alert_rule_id="rule-1", status="firing", opened_at=datetime.now(timezone.utc), triggering_value=2, threshold=1, message="open", alert_rule=rule)
    other_rule = AlertRuleModel(id="rule-2", workspace_id="other-workspace", name="Other", metric="latency", service="billing-service", aggregation="avg", bucket="raw", evaluation_window_seconds=60, operator=">=", threshold=1, evaluation_interval_seconds=60, cooldown_seconds=0, enabled=True, state="firing")
    other_incident = IncidentModel(id="incident-2", workspace_id="other-workspace", alert_rule_id="rule-2", status="firing", opened_at=datetime.now(timezone.utc), triggering_value=2, threshold=1, message="open", alert_rule=other_rule)
    db.add_all([rule, incident, other_rule, other_incident])
    db.commit()

    body = client.get(f"/api/v1/incidents/{incident.id}/impact").json()
    assert body["impactUnavailable"] is True
    assert body["reason"] == "service_not_in_catalog"
    assert client.get(f"/api/v1/incidents/{other_incident.id}/impact").status_code == 404


def test_no_service_and_deleted_catalog_service_are_resilient(intelligence_client: tuple[TestClient, Session, str]) -> None:
    client, db, workspace_id = intelligence_client
    service = _service(db, workspace_id, "auth", "auth-service")
    incident = _rule_and_incident(db, workspace_id, "auth-service")
    IncidentTimelineService(db).record_opened(incident, 600, incident.opened_at)
    db.delete(service)
    db.commit()
    assert client.get(f"/api/v1/incidents/{incident.id}").status_code == 200
    assert client.get(f"/api/v1/incidents/{incident.id}/timeline").json()["events"][0]["metadata"]["service"] == "auth-service"
    assert client.get(f"/api/v1/incidents/{incident.id}/notifications/summary").status_code == 200
    missing = client.get(f"/api/v1/incidents/{incident.id}/impact").json()
    assert missing["impactUnavailable"] is True
    assert missing["reason"] == "service_not_in_catalog"
    no_service = _rule_and_incident(db, workspace_id, None)
    no_service_body = client.get(f"/api/v1/incidents/{no_service.id}/impact").json()
    assert no_service_body["impactUnavailable"] is True
    assert no_service_body["reason"] == "incident_has_no_service"


def test_timeline_failure_rolls_back_open_and_resolve_transitions(intelligence_client: tuple[TestClient, Session, str], monkeypatch: pytest.MonkeyPatch) -> None:
    client, db, workspace_id = intelligence_client
    channel = NotificationChannelModel(id="channel-1", workspace_id=workspace_id, name="Ops", type="webhook", enabled=True, config_json='{"targetUrl":"https://example.com"}')
    db.add(channel)
    _event(db, workspace_id, "rollback-open", 600)
    rule = client.post("/api/v1/alerts", json=_alert_payload()).json()
    db.add(AlertNotificationChannelModel(workspace_id=workspace_id, alert_rule_id=rule["id"], channel_id=channel.id))
    db.commit()

    def fail_open(*_args, **_kwargs):
        raise RuntimeError("timeline down")

    monkeypatch.setattr(IncidentTimelineService, "record_opened", fail_open)
    with pytest.raises(RuntimeError):
        AlertEvaluationService(db).evaluate_rule(rule["id"])
    assert db.scalar(select(func.count(IncidentModel.id)).where(IncidentModel.workspace_id == workspace_id)) == 0
    assert db.scalar(select(func.count(NotificationDeliveryModel.id)).where(NotificationDeliveryModel.workspace_id == workspace_id)) == 0

    monkeypatch.undo()
    opened = AlertEvaluationService(db).evaluate_rule(rule["id"])
    assert opened.incident_id is not None
    client.patch(f"/api/v1/alerts/{rule['id']}", json={"threshold": 1000})

    def fail_resolve(*_args, **_kwargs):
        raise RuntimeError("timeline down")

    monkeypatch.setattr(IncidentTimelineService, "record_resolved", fail_resolve)
    with pytest.raises(RuntimeError):
        AlertEvaluationService(db).evaluate_rule(rule["id"])
    active = db.scalars(select(IncidentModel).where(IncidentModel.id == opened.incident_id)).one()
    assert active.status == "firing"
    assert db.scalar(select(func.count(IncidentEventModel.id)).where(IncidentEventModel.event_type == "incident.resolved")) == 0
    assert db.scalar(select(func.count(NotificationDeliveryModel.id)).where(NotificationDeliveryModel.event_type == "resolved")) == 0


def test_notification_timeline_derivation_order_limit_and_summary_isolation(intelligence_client: tuple[TestClient, Session, str]) -> None:
    client, db, workspace_id = intelligence_client
    incident_a = _rule_and_incident(db, workspace_id, "auth-service")
    incident_b = _rule_and_incident(db, workspace_id, "billing-service")
    base = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)
    IncidentTimelineService(db).record(workspace_id=workspace_id, incident_id=incident_a.id, event_type="incident.opened", title="Opened", occurred_at=base + timedelta(seconds=5), dedupe_key="opened", metadata={"password": "x", "token": "x", "apiKey": "x", "authorization": "x", "cookie": "x", "secret": "x", "webhookSecret": "x"})
    rows = [
        NotificationDeliveryModel(id="a-delivered", workspace_id=workspace_id, alert_rule_id=incident_a.alert_rule_id, incident_id=incident_a.id, channel_id=None, channel_name="Webhook A", channel_type="webhook", channel_config_json="{}", event_type="firing", status="delivered", attempt_count=3, delivered_at=base + timedelta(seconds=1)),
        NotificationDeliveryModel(id="a-failed", workspace_id=workspace_id, alert_rule_id=incident_a.alert_rule_id, incident_id=incident_a.id, channel_id=None, channel_name="Email A", channel_type="email", channel_config_json="{}", event_type="resolved", status="failed", attempt_count=5, last_attempt_at=base + timedelta(seconds=2)),
        NotificationDeliveryModel(id="a-pending", workspace_id=workspace_id, alert_rule_id=incident_a.alert_rule_id, incident_id=incident_a.id, channel_id=None, channel_name="Pending A", channel_type="email", channel_config_json="{}", event_type="firing", status="pending", attempt_count=0),
        NotificationDeliveryModel(id="a-delivering", workspace_id=workspace_id, alert_rule_id=incident_a.alert_rule_id, incident_id=incident_a.id, channel_id=None, channel_name="Delivering A", channel_type="email", channel_config_json="{}", event_type="firing", status="delivering", attempt_count=1),
        NotificationDeliveryModel(id="b-delivered", workspace_id=workspace_id, alert_rule_id=incident_b.alert_rule_id, incident_id=incident_b.id, channel_id=None, channel_name="Webhook B", channel_type="webhook", channel_config_json="{}", event_type="firing", status="delivered", attempt_count=1, delivered_at=base),
    ]
    db.add_all(rows)
    db.commit()
    timeline = client.get(f"/api/v1/incidents/{incident_a.id}/timeline?limit=2").json()
    assert timeline["limited"] is True
    assert len(timeline["events"]) == 2
    assert [event["sourceId"] for event in timeline["events"]] == ["a-delivered", "a-failed"]
    assert timeline["events"][0]["metadata"]["attemptCount"] == 3
    assert timeline["events"][1]["metadata"]["eventType"] == "resolved"
    redacted = client.get(f"/api/v1/incidents/{incident_a.id}/timeline?limit=10").json()["events"][-1]["metadata"]
    assert set(redacted.values()) == {"[REDACTED]"}
    assert client.get(f"/api/v1/incidents/{incident_a.id}/notifications/summary").json()["summary"] == {"pending": 1, "delivering": 1, "delivered": 1, "failed": 1}


def test_trigger_snapshot_and_resolution_value_are_not_overwritten(intelligence_client: tuple[TestClient, Session, str]) -> None:
    client, db, workspace_id = intelligence_client
    t0 = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)
    for event_id, ts, latency in [("snap-open", t0, 600), ("snap-later", t0 + timedelta(minutes=1), 900), ("snap-clear", t0 + timedelta(minutes=2), 200)]:
        db.add(TelemetryEventModel(id=event_id, workspace_id=workspace_id, timestamp=ts, service="auth-service", region="us-east", latency=latency, throughput=1, cpu_usage=1, memory_usage=1, error_rate=0, payload_size=1, status="healthy"))
    db.commit()
    rule = client.post("/api/v1/alerts", json={**_alert_payload(), "evaluationWindowSeconds": 30}).json()
    service = AlertEvaluationService(db)
    opened = service.evaluate_rule(rule["id"], now=t0 + timedelta(seconds=10))
    service.evaluate_rule(rule["id"], now=t0 + timedelta(minutes=1, seconds=10))
    client.patch(f"/api/v1/alerts/{rule['id']}", json={"threshold": 500})
    service.evaluate_rule(rule["id"], now=t0 + timedelta(minutes=2, seconds=10))
    events = client.get(f"/api/v1/incidents/{opened.incident_id}/timeline").json()["events"]
    assert events[0]["metadata"]["observedValue"] == 600
    assert events[-1]["metadata"]["finalObservedValue"] == 200
    assert events[-1]["metadata"]["durationSeconds"] >= 0


def test_cross_workspace_identical_service_names_use_active_graph(intelligence_client: tuple[TestClient, Session, str]) -> None:
    _client, db, workspace_id = intelligence_client
    a_gateway = _service(db, workspace_id, "a-gateway", "api-gateway")
    a_auth = _service(db, workspace_id, "a-auth", "auth-service")
    b_gateway = _service(db, "other-workspace", "b-gateway", "api-gateway")
    b_auth = _service(db, "other-workspace", "b-auth", "auth-service")
    db.add_all([
        ServiceDependencyModel(id="a-edge", workspace_id=workspace_id, source_service=a_gateway, target_service=a_auth, dependency_type="http"),
        ServiceDependencyModel(id="b-edge", workspace_id="other-workspace", source_service=b_auth, target_service=b_gateway, dependency_type="http"),
    ])
    impact = IncidentImpactServiceBuilder(db).impact(_rule_and_incident(db, workspace_id, "auth-service"))
    assert {item.name: item.depth for item in impact.affected_services} == {"auth-service": 0, "api-gateway": 1}


def test_all_workspace_roles_can_read_incident_intelligence() -> None:
    for role in ["owner", "admin", "member", "viewer"]:
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        db = sessionmaker(bind=engine, expire_on_commit=False)()
        app.dependency_overrides[get_alert_repository] = lambda: AlertRepository(db)
        app.dependency_overrides[get_auth_repository] = lambda: AuthRepository(db)
        try:
            with TestClient(app) as client:
                workspace_id = authenticate_test_client(client, db, role=role)
                rule = AlertRuleModel(id=f"rule-{role}", workspace_id=workspace_id, name="Rule", metric="latency", service=None, aggregation="avg", bucket="raw", evaluation_window_seconds=60, operator=">=", threshold=1, evaluation_interval_seconds=60, cooldown_seconds=0, enabled=True, state="normal")
                incident = IncidentModel(id=f"incident-{role}", workspace_id=workspace_id, alert_rule_id=rule.id, status="firing", opened_at=datetime.now(timezone.utc), triggering_value=2, threshold=1, message="open", alert_rule=rule)
                db.add_all([rule, incident])
                db.commit()
                assert client.get(f"/api/v1/incidents/{incident.id}/timeline").status_code == 200
                assert client.get(f"/api/v1/incidents/{incident.id}/impact").status_code == 200
        finally:
            app.dependency_overrides.clear()
            db.close()
