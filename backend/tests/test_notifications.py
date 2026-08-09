from collections.abc import Generator
from datetime import datetime, timedelta, timezone
import hmac
from hashlib import sha256
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_auth_repository
from app.api.v1.routes.alerts import get_alert_evaluator, get_alert_repository, get_notification_repository as get_alert_notification_repository
from app.api.v1.routes.notifications import get_alert_repository as get_notification_alert_repository, get_notification_repository as get_notification_route_repository
from app.core.config import get_settings
from app.db.base import Base
from app.main import app
from app.models.alerts import IncidentModel
from app.models.auth import WorkspaceModel
from app.models.notifications import NotificationDeliveryModel
from app.models.telemetry import TelemetryEventModel
from app.repositories.alerts import AlertRepository
from app.repositories.auth import AuthRepository
from app.repositories.notifications import NotificationRepository
from app.schemas.notifications import NotificationChannelCreate
from app.services.alerts import AlertEvaluationService
from app.repositories.notifications import decrypt_secret
from app.services.notifications import DeliveryResult, NotificationDeliveryService, UnsafeWebhookUrl, validate_webhook_url
from tests.auth_helpers import authenticate_test_client


@pytest.fixture
def notification_db() -> Generator[Session, None, None]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session_local = sessionmaker(bind=engine, expire_on_commit=False)
    db = session_local()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def notification_client(notification_db: Session) -> Generator[tuple[TestClient, str], None, None]:
    app.dependency_overrides[get_auth_repository] = lambda: AuthRepository(notification_db)
    app.dependency_overrides[get_alert_repository] = lambda: AlertRepository(notification_db)
    app.dependency_overrides[get_notification_alert_repository] = lambda: AlertRepository(notification_db)
    app.dependency_overrides[get_alert_evaluator] = lambda: AlertEvaluationService(notification_db)
    app.dependency_overrides[get_alert_notification_repository] = lambda: NotificationRepository(notification_db)
    app.dependency_overrides[get_notification_route_repository] = lambda: NotificationRepository(notification_db)
    with TestClient(app) as client:
        workspace_id = authenticate_test_client(client, notification_db)
        yield client, workspace_id
    app.dependency_overrides.clear()


def insert_point(db: Session, workspace_id: str, latency: float) -> None:
    now = datetime.now(timezone.utc)
    db.add(TelemetryEventModel(
        id=f"notification-test-{latency}-{now.timestamp()}",
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


def alert_payload(channel_id: str | None = None, threshold: float = 100) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": "Notify latency",
        "metric": "latency",
        "aggregation": "avg",
        "bucket": "raw",
        "evaluationWindowSeconds": 300,
        "operator": ">=",
        "threshold": threshold,
        "evaluationIntervalSeconds": 60,
        "cooldownSeconds": 0,
        "enabled": True,
    }
    if channel_id:
        payload["notificationChannelIds"] = [channel_id]
    return payload


def test_channel_crud_redacts_secret_and_enforces_rbac(notification_client: tuple[TestClient, str]) -> None:
    client, _ = notification_client
    created = client.post("/api/v1/notification-channels", json={"name": "Ops", "type": "email", "emailConfig": {"recipients": ["ops@example.com"]}})
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["emailConfig"]["recipients"] == ["ops@example.com"]
    assert "secret" not in created.text
    webhook = client.post("/api/v1/notification-channels", json={"name": "Hook", "type": "webhook", "webhookConfig": {"targetUrl": "https://example.com/hooks/1", "secret": "super-secret"}})
    assert webhook.status_code == 201, webhook.text
    assert webhook.json()["hasSecret"] is True
    assert "super-secret" not in webhook.text
    assert len(client.get("/api/v1/notification-channels").json()["channels"]) == 2
    assert client.patch(f"/api/v1/notification-channels/{body['id']}", json={"enabled": False}).json()["enabled"] is False


def test_alert_association_creates_idempotent_firing_and_resolved_deliveries(notification_client: tuple[TestClient, str], notification_db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    client, workspace_id = notification_client
    monkeypatch.setattr(NotificationDeliveryService, "enqueue_delivery", lambda self, delivery_id: None)
    channel = client.post("/api/v1/notification-channels", json={"name": "Ops", "type": "email", "emailConfig": {"recipients": ["ops@example.com"]}}).json()
    insert_point(notification_db, workspace_id, 250)
    rule = client.post("/api/v1/alerts", json=alert_payload(channel["id"])).json()
    assert rule["notificationChannelIds"] == [channel["id"]]
    first = client.post(f"/api/v1/alerts/{rule['id']}/evaluate").json()
    second = client.post(f"/api/v1/alerts/{rule['id']}/evaluate").json()
    assert second["incidentId"] == first["incidentId"]
    deliveries = notification_db.scalars(select(NotificationDeliveryModel)).all()
    assert [(delivery.event_type, delivery.status) for delivery in deliveries] == [("firing", "pending")]
    client.patch(f"/api/v1/alerts/{rule['id']}", json={"threshold": 1000})
    client.post(f"/api/v1/alerts/{rule['id']}/evaluate")
    deliveries = notification_db.scalars(select(NotificationDeliveryModel).order_by(NotificationDeliveryModel.event_type)).all()
    assert [delivery.event_type for delivery in deliveries] == ["firing", "resolved"]


def test_enqueue_failure_leaves_pending_delivery_recoverable(notification_client: tuple[TestClient, str], notification_db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    client, workspace_id = notification_client
    channel = client.post("/api/v1/notification-channels", json={"name": "Ops", "type": "email", "emailConfig": {"recipients": ["ops@example.com"]}}).json()
    insert_point(notification_db, workspace_id, 250)
    rule = client.post("/api/v1/alerts", json=alert_payload(channel["id"])).json()

    def raise_enqueue(delivery_id: str) -> None:
        raise RuntimeError(f"broker unavailable for {delivery_id}")

    monkeypatch.setattr("app.tasks.notifications.deliver_notification.delay", raise_enqueue)
    response = client.post(f"/api/v1/alerts/{rule['id']}/evaluate")

    assert response.status_code == 200
    delivery = notification_db.scalars(select(NotificationDeliveryModel)).one()
    assert delivery.status == "pending"
    assert delivery.attempt_count == 0
    assert [item.id for item in NotificationRepository(notification_db).due_deliveries()] == [delivery.id]


def test_delivery_claim_success_retry_and_exhaustion(notification_client: tuple[TestClient, str], notification_db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    client, workspace_id = notification_client
    channel = client.post("/api/v1/notification-channels", json={"name": "Ops", "type": "email", "emailConfig": {"recipients": ["ops@example.com"]}}).json()
    insert_point(notification_db, workspace_id, 250)
    rule = client.post("/api/v1/alerts", json=alert_payload(channel["id"])).json()
    monkeypatch.setattr(NotificationDeliveryService, "enqueue_delivery", lambda self, delivery_id: None)
    client.post(f"/api/v1/alerts/{rule['id']}/evaluate")
    delivery = notification_db.scalars(select(NotificationDeliveryModel)).one()

    monkeypatch.setattr(NotificationDeliveryService, "_send", lambda self, delivery, rule, incident: DeliveryResult(delivered=False, retryable=True, response_code=500, error="boom"))
    result = NotificationDeliveryService(notification_db).deliver(delivery.id)
    assert result.retryable is True
    notification_db.refresh(delivery)
    assert delivery.status == "pending"
    assert delivery.next_retry_at is not None

    delivery.attempt_count = get_settings().notification_max_attempts - 1
    notification_db.commit()
    NotificationDeliveryService(notification_db).deliver(delivery.id)
    notification_db.refresh(delivery)
    assert delivery.status == "failed"


def test_delivery_claim_rejects_non_pending_rows(notification_client: tuple[TestClient, str], notification_db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    client, workspace_id = notification_client
    channel = client.post("/api/v1/notification-channels", json={"name": "Ops", "type": "email", "emailConfig": {"recipients": ["ops@example.com"]}}).json()
    insert_point(notification_db, workspace_id, 250)
    rule = client.post("/api/v1/alerts", json=alert_payload(channel["id"])).json()
    monkeypatch.setattr(NotificationDeliveryService, "enqueue_delivery", lambda self, delivery_id: None)
    client.post(f"/api/v1/alerts/{rule['id']}/evaluate")
    delivery = notification_db.scalars(select(NotificationDeliveryModel)).one()
    claimed = NotificationRepository(notification_db).claim_delivery(delivery.id)
    assert claimed is not None
    assert NotificationRepository(notification_db).claim_delivery(delivery.id) is None


def test_stale_delivering_rows_are_recovered(notification_client: tuple[TestClient, str], notification_db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    client, workspace_id = notification_client
    channel = client.post("/api/v1/notification-channels", json={"name": "Ops", "type": "email", "emailConfig": {"recipients": ["ops@example.com"]}}).json()
    insert_point(notification_db, workspace_id, 250)
    rule = client.post("/api/v1/alerts", json=alert_payload(channel["id"])).json()
    monkeypatch.setattr(NotificationDeliveryService, "enqueue_delivery", lambda self, delivery_id: None)
    client.post(f"/api/v1/alerts/{rule['id']}/evaluate")
    delivery = notification_db.scalars(select(NotificationDeliveryModel)).one()
    delivery.status = "delivering"
    delivery.last_attempt_at = datetime.now(timezone.utc) - timedelta(seconds=500)
    notification_db.commit()

    due = NotificationRepository(notification_db).due_deliveries(lease_seconds=120)

    notification_db.refresh(delivery)
    assert [item.id for item in due] == [delivery.id]
    assert delivery.status == "pending"


def test_webhook_signing_and_ssrf_validation(notification_client: tuple[TestClient, str], notification_db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    client, workspace_id = notification_client
    channel = client.post("/api/v1/notification-channels", json={"name": "Hook", "type": "webhook", "webhookConfig": {"targetUrl": "https://example.com/webhook", "secret": "signing-secret"}}).json()
    insert_point(notification_db, workspace_id, 250)
    rule = client.post("/api/v1/alerts", json=alert_payload(channel["id"])).json()
    monkeypatch.setattr(NotificationDeliveryService, "enqueue_delivery", lambda self, delivery_id: None)
    client.post(f"/api/v1/alerts/{rule['id']}/evaluate")
    delivery = notification_db.scalars(select(NotificationDeliveryModel)).one()
    captured: dict[str, object] = {}

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            return None

        def post(self, url, content, headers):
            captured.update({"url": url, "content": content, "headers": headers})
            return SimpleNamespace(status_code=204)

    monkeypatch.setattr("app.services.notifications.httpx.Client", FakeClient)
    result = NotificationDeliveryService(notification_db).deliver(delivery.id)
    assert result.delivered is True
    assert captured["url"] == "https://example.com/webhook"
    headers = captured["headers"]
    assert isinstance(headers, dict)
    assert str(headers["x-observa-signature"]).startswith("sha256=")
    assert headers["x-observa-delivery-id"] == delivery.id
    assert f'"deliveryId":"{delivery.id}"'.encode("utf-8") in captured["content"]
    expected = hmac.new(b"signing-secret", str(headers["x-observa-timestamp"]).encode("utf-8") + b"." + captured["content"], sha256).hexdigest()
    assert headers["x-observa-signature"] == f"sha256={expected}"
    with pytest.raises(UnsafeWebhookUrl):
        validate_webhook_url("http://127.0.0.1:8080/hook")
    with pytest.raises(UnsafeWebhookUrl):
        validate_webhook_url("https://127.0.0.1/hook")
    with pytest.raises(UnsafeWebhookUrl):
        validate_webhook_url("https://[::1]/hook")


def test_webhook_secret_patch_preserves_and_replaces_secret(notification_client: tuple[TestClient, str], notification_db: Session) -> None:
    client, _ = notification_client
    created = client.post("/api/v1/notification-channels", json={"name": "Hook", "type": "webhook", "webhookConfig": {"targetUrl": "https://example.com/webhook", "secret": "first-secret"}}).json()
    repo = NotificationRepository(notification_db)
    channel = repo.get_channel(created["workspaceId"], created["id"])
    assert channel is not None and channel.secret_encrypted is not None
    first = decrypt_secret(channel.secret_encrypted)
    patched = client.patch(f"/api/v1/notification-channels/{created['id']}", json={"name": "Renamed", "webhookConfig": {"targetUrl": "https://example.com/webhook"}})
    assert patched.status_code == 200
    notification_db.refresh(channel)
    assert decrypt_secret(channel.secret_encrypted or "") == first
    replaced = client.patch(f"/api/v1/notification-channels/{created['id']}", json={"webhookConfig": {"targetUrl": "https://example.com/webhook", "secret": "second-secret"}})
    assert replaced.status_code == 200
    notification_db.refresh(channel)
    assert decrypt_secret(channel.secret_encrypted or "") == "second-secret"


def test_deleted_channel_pending_delivery_uses_snapshot(notification_client: tuple[TestClient, str], notification_db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    client, workspace_id = notification_client
    channel = client.post("/api/v1/notification-channels", json={"name": "Ops", "type": "email", "emailConfig": {"recipients": ["ops@example.com"]}}).json()
    insert_point(notification_db, workspace_id, 250)
    rule = client.post("/api/v1/alerts", json=alert_payload(channel["id"])).json()
    monkeypatch.setattr(NotificationDeliveryService, "enqueue_delivery", lambda self, delivery_id: None)
    client.post(f"/api/v1/alerts/{rule['id']}/evaluate")
    delivery = notification_db.scalars(select(NotificationDeliveryModel)).one()
    assert client.delete(f"/api/v1/notification-channels/{channel['id']}").status_code == 204
    notification_db.refresh(delivery)
    assert delivery.channel_id is None

    monkeypatch.setattr(NotificationDeliveryService, "_send", lambda self, delivery, rule, incident: DeliveryResult(delivered=True, retryable=False))
    result = NotificationDeliveryService(notification_db).deliver(delivery.id)

    assert result.delivered is True
    notification_db.refresh(delivery)
    assert delivery.status == "delivered"


def test_delivery_history_is_workspace_scoped(notification_client: tuple[TestClient, str], notification_db: Session) -> None:
    client, workspace_id = notification_client
    other_workspace = WorkspaceModel(name="Other", slug="other")
    notification_db.add(other_workspace)
    notification_db.flush()
    notification_db.add(NotificationDeliveryModel(workspace_id=other_workspace.id, alert_rule_id=None, incident_id=None, channel_id=None, channel_name="Other", channel_type="email", channel_config_json='{"recipients":["x@example.com"]}', event_type="test", status="pending", attempt_count=0))
    notification_db.commit()
    other_delivery_id = notification_db.scalars(select(NotificationDeliveryModel.id).where(NotificationDeliveryModel.workspace_id == other_workspace.id)).one()
    assert client.get("/api/v1/notification-deliveries").json()["deliveries"] == []
    assert client.get(f"/api/v1/notification-deliveries/{other_delivery_id}").status_code == 404
    assert client.post("/api/v1/notification-channels", json={"name": "Bad", "type": "webhook", "webhookConfig": {"targetUrl": "ftp://example.com"}}).status_code == 422


def test_cross_workspace_channel_cannot_attach_to_alert(notification_client: tuple[TestClient, str], notification_db: Session) -> None:
    client, workspace_id = notification_client
    other_workspace = WorkspaceModel(name="Other attach", slug="other-attach")
    notification_db.add(other_workspace)
    notification_db.flush()
    other_channel = NotificationRepository(notification_db).create_channel(other_workspace.id, NotificationChannelCreate(name="Other", type="email", email_config={"recipients": ["other@example.com"]}))
    rule = client.post("/api/v1/alerts", json=alert_payload()).json()
    response = client.put(f"/api/v1/alerts/{rule['id']}/notification-channels", json={"channelIds": [other_channel.id]})
    assert response.status_code == 422
