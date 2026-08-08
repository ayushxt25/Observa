from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1.routes.dashboards import get_dashboard_repository
from app.db.base import Base
from app.main import app
from app.models.dashboard import DashboardWidgetModel
from app.repositories.dashboards import DashboardRepository


@pytest.fixture
def dashboard_client() -> Generator[TestClient, None, None]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session_local = sessionmaker(bind=engine, expire_on_commit=False)

    def override_repo() -> Generator[DashboardRepository, None, None]:
        db: Session = session_local()
        try:
            yield DashboardRepository(db)
        finally:
            db.close()

    app.dependency_overrides[get_dashboard_repository] = override_repo
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def widget_payload(position: int = 0) -> dict[str, object]:
    return {
        "title": f"Latency {position}",
        "type": "line",
        "metric": "latency",
        "aggregation": "avg",
        "bucket": "1m",
        "timeRange": "15m",
        "position": position,
        "thresholdWarning": 150,
        "thresholdCritical": 250,
    }


def create_dashboard(client: TestClient) -> dict[str, object]:
    response = client.post("/api/v1/dashboards", json={"name": "Ops", "widgets": [widget_payload(1), widget_payload(0)]})
    assert response.status_code == 201
    return response.json()


def test_create_list_get_update_delete_dashboard(dashboard_client: TestClient) -> None:
    dashboard = create_dashboard(dashboard_client)
    dashboard_id = dashboard["id"]
    assert [widget["position"] for widget in dashboard["widgets"]] == [0, 1]

    listed = dashboard_client.get("/api/v1/dashboards")
    assert listed.status_code == 200
    assert listed.json()["dashboards"][0]["name"] == "Ops"

    fetched = dashboard_client.get(f"/api/v1/dashboards/{dashboard_id}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == dashboard_id

    renamed = dashboard_client.patch(f"/api/v1/dashboards/{dashboard_id}", json={"name": "Platform Ops"})
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Platform Ops"

    deleted = dashboard_client.delete(f"/api/v1/dashboards/{dashboard_id}")
    assert deleted.status_code == 204
    assert dashboard_client.get(f"/api/v1/dashboards/{dashboard_id}").status_code == 404


def test_widget_create_update_delete_and_ordering(dashboard_client: TestClient) -> None:
    dashboard = create_dashboard(dashboard_client)
    dashboard_id = dashboard["id"]

    created = dashboard_client.post(f"/api/v1/dashboards/{dashboard_id}/widgets", json={**widget_payload(2), "type": "stat"})
    assert created.status_code == 201
    widget_id = created.json()["id"]

    updated = dashboard_client.patch(f"/api/v1/dashboards/{dashboard_id}/widgets/{widget_id}", json={"position": 0, "thresholdCritical": 300})
    assert updated.status_code == 200
    assert updated.json()["thresholdCritical"] == 300

    fetched = dashboard_client.get(f"/api/v1/dashboards/{dashboard_id}")
    assert [widget["position"] for widget in fetched.json()["widgets"]] == [0, 0, 1]

    deleted = dashboard_client.delete(f"/api/v1/dashboards/{dashboard_id}/widgets/{widget_id}")
    assert deleted.status_code == 204
    assert dashboard_client.patch(f"/api/v1/dashboards/{dashboard_id}/widgets/{widget_id}", json={"title": "Missing"}).status_code == 404


def test_widget_full_edit_and_ownership_mismatch(dashboard_client: TestClient) -> None:
    first = create_dashboard(dashboard_client)
    second = dashboard_client.post("/api/v1/dashboards", json={"name": "Other"}).json()
    widget_id = first["widgets"][0]["id"]
    payload = {
        "title": "Edited CPU",
        "type": "stat",
        "metric": "cpuUsage",
        "service": "api-gateway",
        "region": "us-east",
        "aggregation": "max",
        "bucket": "5m",
        "timeRange": "1h",
        "thresholdWarning": 80,
        "thresholdCritical": 90,
    }
    response = dashboard_client.patch(f"/api/v1/dashboards/{first['id']}/widgets/{widget_id}", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == widget_id
    assert body["title"] == "Edited CPU"
    assert body["position"] == first["widgets"][0]["position"]
    assert dashboard_client.patch(f"/api/v1/dashboards/{second['id']}/widgets/{widget_id}", json={"title": "Nope"}).status_code == 404


def test_invalid_widget_inputs_and_missing_resources(dashboard_client: TestClient) -> None:
    assert dashboard_client.get("/api/v1/dashboards/missing").status_code == 404
    invalid = dashboard_client.post("/api/v1/dashboards", json={"name": "Bad", "widgets": [{**widget_payload(), "type": "pie"}]})
    assert invalid.status_code == 422
    invalid_threshold = dashboard_client.post("/api/v1/dashboards", json={"name": "Bad", "widgets": [{**widget_payload(), "thresholdWarning": 500, "thresholdCritical": 100}]})
    assert invalid_threshold.status_code == 422
    unknown = dashboard_client.post("/api/v1/dashboards", json={"name": "Bad", "unexpected": True})
    assert unknown.status_code == 422
    non_finite = dashboard_client.post("/api/v1/dashboards", json={"name": "Bad", "widgets": [{**widget_payload(), "thresholdWarning": "NaN"}]})
    assert non_finite.status_code == 422


def test_empty_dashboard_and_cascade_delete(dashboard_client: TestClient) -> None:
    dashboard = dashboard_client.post("/api/v1/dashboards", json={"name": "Empty"}).json()
    assert dashboard["widgets"] == []
    widget = dashboard_client.post(f"/api/v1/dashboards/{dashboard['id']}/widgets", json=widget_payload()).json()
    assert widget["dashboardId"] == dashboard["id"]
    assert dashboard_client.delete(f"/api/v1/dashboards/{dashboard['id']}").status_code == 204

    repo = next(app.dependency_overrides[get_dashboard_repository]())
    assert repo.db.scalars(select(DashboardWidgetModel)).all() == []
