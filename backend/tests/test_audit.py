from collections.abc import Generator
from datetime import datetime, timezone
import json

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_auth_repository
from app.api.v1.routes.audit import get_audit_repository
from app.api.v1.routes.dashboards import get_dashboard_repository
from app.db.base import Base
from app.main import app
from app.models.audit import AuditEventModel
from app.models.dashboard import DashboardModel
from app.repositories.auth import AuthRepository
from app.repositories.audit import AuditRepository
from app.repositories.dashboards import DashboardRepository
from app.services.audit import AuditService, sanitize_metadata
from tests.auth_helpers import authenticate_test_client


@pytest.fixture
def audit_client() -> Generator[tuple[TestClient, Session, str], None, None]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, expire_on_commit=False)()
    app.dependency_overrides[get_auth_repository] = lambda: AuthRepository(db)
    app.dependency_overrides[get_dashboard_repository] = lambda: DashboardRepository(db)
    app.dependency_overrides[get_audit_repository] = lambda: AuditRepository(db)
    try:
        with TestClient(app) as client:
            workspace_id = authenticate_test_client(client, db)
            yield client, db, workspace_id
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_sanitize_metadata_redacts_nested_secrets() -> None:
    secret_keys = {
        "password": "x",
        "Password": "x",
        "PASSWORD": "x",
        "password_hash": "x",
        "passwordHash": "x",
        "refresh_token": "x",
        "refreshToken": "x",
        "accessToken": "x",
        "apiKey": "x",
        "api_key": "x",
        "authorization": "x",
        "Authorization": "x",
        "cookie": "x",
        "set-cookie": "x",
        "secret": "x",
        "webhookSecret": "x",
        "smtpPassword": "x",
    }
    result = sanitize_metadata({"nested": secret_keys, "items": [{"authorization": "Bearer x"}], "safe": "ok"})
    assert result["safe"] == "ok"
    assert result["items"] == [{"authorization": "[REDACTED]"}]
    assert all(value == "[REDACTED]" for value in result["nested"].values())


def test_dashboard_mutation_creates_workspace_scoped_audit_event(audit_client: tuple[TestClient, Session, str]) -> None:
    client, _db, _workspace_id = audit_client
    created = client.post("/api/v1/dashboards", json={"name": "Audit dashboard", "widgets": []})
    assert created.status_code == 201, created.text
    events = client.get("/api/v1/audit-events").json()["events"]
    assert events[0]["action"] == "dashboard.created"
    assert events[0]["resourceId"] == created.json()["id"]
    assert events[0]["metadata"]["name"] == "Audit dashboard"
    assert "X-Request-Id" in created.headers
    assert created.headers["X-Request-Id"] != "evil\nid"


def test_audit_events_are_admin_only_and_bounded(audit_client: tuple[TestClient, Session, str]) -> None:
    client, db, workspace_id = audit_client
    client.post("/api/v1/dashboards", json={"name": "Audit dashboard", "widgets": []})
    user = AuthRepository(db).get_user_by_email("owner@example.com")
    assert user is not None
    membership = AuthRepository(db).get_membership(user.id, workspace_id)
    assert membership is not None
    membership.role = "member"
    db.commit()
    assert client.get("/api/v1/audit-events?limit=500").status_code == 403
    membership.role = "viewer"
    db.commit()
    assert client.get("/api/v1/audit-events").status_code == 403
    membership.role = "admin"
    db.commit()
    assert client.get("/api/v1/audit-events").status_code == 200
    assert client.get("/api/v1/audit-events?limit=0").status_code == 422
    assert client.get("/api/v1/audit-events?cursor=not-a-real-cursor").status_code == 422


def test_audit_insert_failure_rolls_back_dashboard_mutation(audit_client: tuple[TestClient, Session, str], monkeypatch: pytest.MonkeyPatch) -> None:
    client, db, workspace_id = audit_client

    def fail_create(self, **kwargs):
        raise RuntimeError("audit storage unavailable")

    monkeypatch.setattr(AuditRepository, "create", fail_create)
    with pytest.raises(RuntimeError):
        client.post("/api/v1/dashboards", json={"name": "Should rollback", "widgets": []})
    db.rollback()
    assert db.scalars(select(DashboardModel).where(DashboardModel.workspace_id == workspace_id, DashboardModel.name == "Should rollback")).first() is None


def test_domain_validation_failure_does_not_write_success_audit(audit_client: tuple[TestClient, Session, str]) -> None:
    client, db, _workspace_id = audit_client
    response = client.post("/api/v1/dashboards", json={"widgets": []})
    assert response.status_code == 422
    assert db.scalars(select(AuditEventModel)).all() == []


def test_audit_tenancy_filters_and_cursor_are_deterministic(audit_client: tuple[TestClient, Session, str]) -> None:
    client, db, workspace_id = audit_client
    other_workspace = "other-workspace"
    fixed = datetime(2026, 8, 9, 12, 0, 0, tzinfo=timezone.utc)
    rows = [
        AuditEventModel(id="event-c", workspace_id=workspace_id, actor_type="user", actor_user_id="actor-2", action="alert.created", resource_type="alert_rule", resource_id="c", outcome="failure", metadata_json=json.dumps({"safe": "three"}), created_at=fixed),
        AuditEventModel(id="event-b", workspace_id=workspace_id, actor_type="user", actor_user_id="actor-1", action="dashboard.updated", resource_type="dashboard", resource_id="b", outcome="success", metadata_json=json.dumps({"safe": "two"}), created_at=fixed),
        AuditEventModel(id="event-a", workspace_id=workspace_id, actor_type="user", actor_user_id="actor-1", action="dashboard.created", resource_type="dashboard", resource_id="a", outcome="success", metadata_json=json.dumps({"safe": "one"}), created_at=fixed),
        AuditEventModel(id="event-other", workspace_id=other_workspace, actor_type="user", actor_user_id="actor-1", action="dashboard.created", resource_type="dashboard", resource_id="secret", outcome="success", metadata_json=json.dumps({"safe": "other"}), created_at=fixed),
    ]
    db.add_all(rows)
    db.commit()

    page_one = client.get("/api/v1/audit-events?limit=2").json()
    page_two = client.get(f"/api/v1/audit-events?limit=2&cursor={page_one['nextCursor']}").json()
    ids_one = {event["id"] for event in page_one["events"]}
    ids_two = {event["id"] for event in page_two["events"]}
    assert ids_one.isdisjoint(ids_two)
    assert len(ids_one | ids_two) == 3
    filtered = client.get("/api/v1/audit-events?action=dashboard.created&actorUserId=actor-1&resourceType=dashboard&resourceId=a&outcome=success").json()["events"]
    assert [event["resourceId"] for event in filtered] == ["a"]
    assert client.get(f"/api/v1/audit-events/{db.scalars(select(AuditEventModel.id).where(AuditEventModel.workspace_id == other_workspace)).first()}").status_code == 404


def test_known_secret_values_are_redacted_from_metadata(audit_client: tuple[TestClient, Session, str]) -> None:
    _client, db, workspace_id = audit_client
    values = ["test-password-123", "obs_live_prefix_secret", "webhook-signing-secret", "refresh-token-value", "access-token-value"]
    AuditService(db).record(
        workspace_id=workspace_id,
        actor_type="user",
        action="dashboard.updated",
        resource_type="dashboard",
        outcome="success",
        metadata={"password": values[0], "apiKey": values[1], "webhookSecret": values[2], "refreshToken": values[3], "accessToken": values[4], "safe": "ok"},
    )
    stored = db.scalars(select(AuditEventModel.metadata_json)).one()
    assert all(value not in stored for value in values)
