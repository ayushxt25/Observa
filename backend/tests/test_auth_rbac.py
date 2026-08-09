from collections.abc import Generator
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_auth_repository
from app.api.deps import get_api_key_repository
from app.api.v1.routes import auth as auth_routes
from app.api.v1.routes.alerts import get_alert_repository
from app.api.v1.routes.dashboards import get_dashboard_repository
from app.api.v1.routes.telemetry import get_ingestion_service
from app.db.base import Base
from app.main import app
from app.models.auth import AuthSessionModel, UserModel, WorkspaceApiKeyModel
from app.repositories.auth import AuthRepository
from app.repositories.alerts import AlertRepository
from app.repositories.api_keys import ApiKeyRepository
from app.repositories.dashboards import DashboardRepository
from app.schemas.telemetry import IngestionResponse


@pytest.fixture
def auth_client() -> Generator[tuple[TestClient, Session], None, None]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session_local = sessionmaker(bind=engine, expire_on_commit=False)
    db = session_local()
    original_rate_limit = auth_routes.check_auth_rate_limit
    auth_routes.check_auth_rate_limit = lambda *args, **kwargs: None
    app.dependency_overrides[get_auth_repository] = lambda: AuthRepository(db)
    app.dependency_overrides[get_api_key_repository] = lambda: ApiKeyRepository(db)
    app.dependency_overrides[get_dashboard_repository] = lambda: DashboardRepository(db)
    app.dependency_overrides[get_alert_repository] = lambda: AlertRepository(db)
    with TestClient(app) as client:
        yield client, db
    auth_routes.check_auth_rate_limit = original_rate_limit
    app.dependency_overrides.clear()
    db.close()


def register(client: TestClient, email: str) -> dict[str, object]:
    response = client.post("/api/v1/auth/register", json={"email": email, "password": "strong-password-123", "displayName": email.split("@")[0]})
    assert response.status_code == 201, response.text
    return response.json()


def auth_headers(result: dict[str, object], workspace_id: str | None = None) -> dict[str, str]:
    workspaces = result["workspaces"]
    assert isinstance(workspaces, list)
    selected = workspace_id or workspaces[0]["id"]
    return {"Authorization": f"Bearer {result['accessToken']}", "X-Workspace-Id": str(selected)}


def event_payload(event_id: str = "event-1") -> dict[str, object]:
    return {
        "id": event_id,
        "timestamp": "2026-08-09T00:00:00Z",
        "service": "api-gateway",
        "region": "us-east",
        "latency": 100,
        "throughput": 200,
        "cpuUsage": 30,
        "memoryUsage": 40,
        "errorRate": 0,
        "payloadSize": 100,
        "status": "healthy",
    }


class FakeIngestionService:
    async def ingest(self, workspace_id: str, events: list[object]) -> IngestionResponse:
        return IngestionResponse(accepted_count=len(events), rejected_count=0, processing_duration_ms=1)


def test_register_login_me_and_password_not_exposed(auth_client: tuple[TestClient, Session]) -> None:
    client, db = auth_client
    result = register(client, "User@Example.com")
    assert result["user"]["email"] == "user@example.com"
    assert "passwordHash" not in result["user"]
    assert result["workspaces"][0]["role"] == "owner"
    assert client.post("/api/v1/auth/register", json={"email": "user@example.com", "password": "strong-password-123"}).status_code == 409
    assert client.post("/api/v1/auth/login", json={"email": "user@example.com", "password": "wrong"}).status_code == 401
    login = client.post("/api/v1/auth/login", json={"email": "user@example.com", "password": "strong-password-123"})
    assert login.status_code == 200
    me = client.get("/api/v1/auth/me", headers=auth_headers(login.json()))
    assert me.status_code == 200
    user = db.query(UserModel).filter_by(email="user@example.com").one()
    assert user.password_hash != "strong-password-123"


def test_refresh_rotation_logout_and_token_type_separation(auth_client: tuple[TestClient, Session]) -> None:
    client, db = auth_client
    result = register(client, "rotate@example.com")
    old_cookie = client.cookies.get("observa_refresh")
    assert old_cookie
    refreshed = client.post("/api/v1/auth/refresh")
    assert refreshed.status_code == 200
    new_cookie = client.cookies.get("observa_refresh")
    assert new_cookie and new_cookie != old_cookie
    client.cookies.set("observa_refresh", old_cookie)
    assert client.post("/api/v1/auth/refresh").status_code == 401
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {new_cookie}"}).status_code == 401
    client.cookies.set("observa_refresh", new_cookie)
    assert client.post("/api/v1/auth/logout").status_code == 204
    assert client.post("/api/v1/auth/refresh").status_code == 401
    assert db.query(AuthSessionModel).count() >= 2
    sessions = db.query(AuthSessionModel).all()
    assert all(session.token_hash not in {old_cookie, new_cookie} for session in sessions)
    assert all(len(session.token_hash) == 64 for session in sessions)
    assert client.post("/api/v1/auth/refresh", headers=auth_headers(result)).status_code == 401


def test_disabled_user_cannot_refresh(auth_client: tuple[TestClient, Session]) -> None:
    client, db = auth_client
    register(client, "disabled@example.com")
    user = db.query(UserModel).filter_by(email="disabled@example.com").one()
    user.is_active = False
    db.commit()
    assert client.post("/api/v1/auth/refresh").status_code == 401


def test_workspace_rbac_and_cross_workspace_dashboard_denial(auth_client: tuple[TestClient, Session]) -> None:
    client, _ = auth_client
    owner = register(client, "owner@example.com")
    owner_workspace = owner["workspaces"][0]["id"]
    created = client.post("/api/v1/dashboards", json={"name": "Private"}, headers=auth_headers(owner))
    assert created.status_code == 201
    dashboard_id = created.json()["id"]

    viewer = register(client, "viewer@example.com")
    viewer_workspace = viewer["workspaces"][0]["id"]
    assert client.get(f"/api/v1/dashboards/{dashboard_id}", headers=auth_headers(viewer, str(owner_workspace))).status_code == 403
    assert client.get(f"/api/v1/dashboards/{dashboard_id}", headers=auth_headers(viewer, str(viewer_workspace))).status_code == 404

    add = client.post(
        f"/api/v1/workspaces/{owner_workspace}/members",
        json={"email": "viewer@example.com", "role": "viewer"},
        headers=auth_headers(owner),
    )
    assert add.status_code == 201
    assert client.get("/api/v1/dashboards", headers=auth_headers(viewer, str(owner_workspace))).status_code == 200
    assert client.post("/api/v1/dashboards", json={"name": "Nope"}, headers=auth_headers(viewer, str(owner_workspace))).status_code == 403
    remove = client.delete(f"/api/v1/workspaces/{owner_workspace}/members/{viewer['user']['id']}", headers=auth_headers(owner))
    assert remove.status_code == 204
    assert client.get("/api/v1/dashboards", headers=auth_headers(viewer, str(owner_workspace))).status_code == 403


def test_cross_workspace_widget_alert_and_incident_idor(auth_client: tuple[TestClient, Session]) -> None:
    client, _ = auth_client
    owner = register(client, "idor-owner@example.com")
    workspace_id = owner["workspaces"][0]["id"]
    other = register(client, "idor-other@example.com")
    other_workspace = other["workspaces"][0]["id"]
    dashboard = client.post(
        "/api/v1/dashboards",
        json={
            "name": "Private",
            "widgets": [{"title": "Latency", "type": "line", "metric": "latency", "aggregation": "avg", "bucket": "1m"}],
        },
        headers=auth_headers(owner),
    )
    assert dashboard.status_code == 201
    dashboard_body = dashboard.json()
    widget_id = dashboard_body["widgets"][0]["id"]
    assert (
        client.patch(
            f"/api/v1/dashboards/{dashboard_body['id']}/widgets/{widget_id}",
            json={"title": "Stolen"},
            headers=auth_headers(other, str(other_workspace)),
        ).status_code
        == 404
    )
    alert = client.post(
        "/api/v1/alerts",
        json={
            "name": "Private alert",
            "metric": "latency",
            "aggregation": "avg",
            "bucket": "1m",
            "operator": ">",
            "threshold": 1,
            "evaluationIntervalSeconds": 60,
            "cooldownSeconds": 0,
        },
        headers=auth_headers(owner, str(workspace_id)),
    )
    assert alert.status_code == 201
    alert_id = alert.json()["id"]
    assert client.get(f"/api/v1/alerts/{alert_id}", headers=auth_headers(other, str(other_workspace))).status_code == 404
    assert client.patch(f"/api/v1/alerts/{alert_id}", json={"enabled": False}, headers=auth_headers(other, str(other_workspace))).status_code == 404
    assert client.post(f"/api/v1/alerts/{alert_id}/evaluate", headers=auth_headers(other, str(other_workspace))).status_code == 404


def test_final_owner_cannot_be_demoted(auth_client: tuple[TestClient, Session]) -> None:
    client, _ = auth_client
    owner = register(client, "final-owner@example.com")
    workspace_id = owner["workspaces"][0]["id"]
    user_id = owner["user"]["id"]
    response = client.patch(f"/api/v1/workspaces/{workspace_id}/members/{user_id}", json={"role": "admin"}, headers=auth_headers(owner))
    assert response.status_code == 409
    assert client.delete(f"/api/v1/workspaces/{workspace_id}/members/{user_id}", headers=auth_headers(owner)).status_code == 409


def test_admin_cannot_manage_owner_or_promote_to_owner(auth_client: tuple[TestClient, Session]) -> None:
    client, _ = auth_client
    owner = register(client, "owner-admin@example.com")
    admin = register(client, "admin-user@example.com")
    workspace_id = owner["workspaces"][0]["id"]
    add = client.post(
        f"/api/v1/workspaces/{workspace_id}/members",
        json={"email": "admin-user@example.com", "role": "admin"},
        headers=auth_headers(owner),
    )
    assert add.status_code == 201
    assert client.patch(f"/api/v1/workspaces/{workspace_id}/members/{owner['user']['id']}", json={"role": "member"}, headers=auth_headers(admin, str(workspace_id))).status_code == 403
    assert client.patch(f"/api/v1/workspaces/{workspace_id}/members/{admin['user']['id']}", json={"role": "owner"}, headers=auth_headers(admin, str(workspace_id))).status_code == 403


def test_auth_rate_limit_dependency_returns_429(auth_client: tuple[TestClient, Session], monkeypatch: pytest.MonkeyPatch) -> None:
    client, _ = auth_client

    def always_limited(*args: object, **kwargs: object) -> None:
        from fastapi import HTTPException, status

        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many authentication attempts")

    monkeypatch.setattr(auth_routes, "check_auth_rate_limit", always_limited)
    response = client.post("/api/v1/auth/login", json={"email": "limited@example.com", "password": "password"})
    assert response.status_code == 429


def test_auth_schemas_reject_unknown_fields(auth_client: tuple[TestClient, Session]) -> None:
    client, _ = auth_client
    response = client.post("/api/v1/auth/register", json={"email": "strict@example.com", "password": "strong-password-123", "isActive": True})
    assert response.status_code == 422


def test_workspace_api_key_lifecycle_and_permissions(auth_client: tuple[TestClient, Session]) -> None:
    client, db = auth_client
    owner = register(client, "key-owner@example.com")
    workspace_id = owner["workspaces"][0]["id"]
    created = client.post(f"/api/v1/workspaces/{workspace_id}/api-keys", json={"name": "Generator"}, headers=auth_headers(owner))
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["rawKey"].startswith("obs_live_")
    assert "keyHash" not in body
    stored = db.query(WorkspaceApiKeyModel).filter_by(id=body["id"]).one()
    assert stored.key_hash != body["rawKey"]
    listed = client.get(f"/api/v1/workspaces/{workspace_id}/api-keys", headers=auth_headers(owner))
    assert listed.status_code == 200
    assert "rawKey" not in listed.text and "keyHash" not in listed.text

    viewer = register(client, "key-viewer@example.com")
    add = client.post(f"/api/v1/workspaces/{workspace_id}/members", json={"email": "key-viewer@example.com", "role": "viewer"}, headers=auth_headers(owner))
    assert add.status_code == 201
    assert client.post(f"/api/v1/workspaces/{workspace_id}/api-keys", json={"name": "Nope"}, headers=auth_headers(viewer, str(workspace_id))).status_code == 403

    revoked = client.delete(f"/api/v1/workspaces/{workspace_id}/api-keys/{body['id']}", headers=auth_headers(owner))
    assert revoked.status_code == 204


def test_workspace_api_key_ingestion_and_revocation(auth_client: tuple[TestClient, Session]) -> None:
    client, _ = auth_client
    owner = register(client, "ingest-key@example.com")
    workspace_id = owner["workspaces"][0]["id"]
    created = client.post(f"/api/v1/workspaces/{workspace_id}/api-keys", json={"name": "Generator"}, headers=auth_headers(owner))
    raw_key = created.json()["rawKey"]
    app.dependency_overrides[get_ingestion_service] = lambda: FakeIngestionService()
    assert client.post("/api/v1/telemetry", json={**event_payload(), "workspaceId": "attacker"}, headers={"Authorization": f"Bearer {raw_key}"}).status_code == 422
    assert client.post("/api/v1/telemetry", json=event_payload(), headers={"Authorization": f"Bearer {raw_key}"}).status_code == 202
    prefix_collision = raw_key.rsplit("_", 1)[0] + "_wrong-secret"
    assert client.post("/api/v1/telemetry", json=event_payload("event-prefix"), headers={"Authorization": f"Bearer {prefix_collision}"}).status_code == 401
    client.delete(f"/api/v1/workspaces/{workspace_id}/api-keys/{created.json()['id']}", headers=auth_headers(owner))
    assert client.post("/api/v1/telemetry", json=event_payload("event-2"), headers={"Authorization": f"Bearer {raw_key}"}).status_code == 401


def test_expired_workspace_api_key_is_rejected(auth_client: tuple[TestClient, Session]) -> None:
    client, _ = auth_client
    owner = register(client, "expired-key@example.com")
    workspace_id = owner["workspaces"][0]["id"]
    created = client.post(
        f"/api/v1/workspaces/{workspace_id}/api-keys",
        json={"name": "Expired", "expiresAt": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()},
        headers=auth_headers(owner),
    )
    assert created.status_code == 201
    app.dependency_overrides[get_ingestion_service] = lambda: FakeIngestionService()
    assert client.post(
        "/api/v1/telemetry",
        json=event_payload("expired-key-event"),
        headers={"Authorization": f"Bearer {created.json()['rawKey']}"},
    ).status_code == 401
