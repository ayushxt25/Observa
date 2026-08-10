from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_auth_repository
from app.api.v1.routes.query import get_query_engine
from app.db.base import Base
from app.main import app
from app.models.auth import UserModel, WorkspaceMembershipModel, WorkspaceModel
from app.models.telemetry import TelemetryEventModel
from app.query.engine import TelemetryQueryEngine
from app.repositories.auth import AuthRepository
from tests.auth_helpers import authenticate_test_client


def _event(
    event_id: str,
    workspace_id: str,
    timestamp: datetime,
    *,
    service: str = "api-gateway",
    region: str = "us-east",
    status: str = "healthy",
    latency: float = 100,
    error_rate: float = 1,
    throughput: float = 10,
) -> TelemetryEventModel:
    return TelemetryEventModel(
        id=event_id,
        workspace_id=workspace_id,
        timestamp=timestamp,
        service=service,
        region=region,
        latency=latency,
        throughput=throughput,
        cpu_usage=latency / 10,
        memory_usage=latency / 20,
        error_rate=error_rate,
        payload_size=int(latency),
        status=status,
    )


@pytest.fixture
def query_client() -> tuple[TestClient, Session, str, datetime]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, expire_on_commit=False)()
    app.dependency_overrides[get_auth_repository] = lambda: AuthRepository(db)
    app.dependency_overrides[get_query_engine] = lambda: TelemetryQueryEngine(db, max_range_seconds=3600, max_points=50, max_groups=2)
    now = datetime(2026, 8, 10, 0, 0, tzinfo=timezone.utc)
    try:
        with TestClient(app) as client:
            workspace_id = authenticate_test_client(client, db)
            db.add_all([
                _event("e1", workspace_id, now, service="api-gateway", region="us-east", latency=10, error_rate=0.5, throughput=1),
                _event("e2", workspace_id, now + timedelta(seconds=10), service="api-gateway", region="us-east", latency=20, error_rate=1.5, throughput=2, status="degraded"),
                _event("e3", workspace_id, now + timedelta(seconds=70), service="auth-service", region="us-west", latency=30, error_rate=2.5, throughput=3),
                _event("e4", workspace_id, now + timedelta(seconds=130), service="auth-service", region="us-west", latency=40, error_rate=3.5, throughput=4, status="critical"),
                _event("other", "workspace-other", now + timedelta(seconds=20), service="leaked", region="us-east", latency=999, throughput=999),
            ])
            db.commit()
            yield client, db, workspace_id, now
    finally:
        app.dependency_overrides.clear()
        db.close()


def _query(client: TestClient, now: datetime, **overrides):
    payload = {
        "metric": "latency",
        "aggregation": "avg",
        "start": now.isoformat(),
        "end": (now + timedelta(minutes=5)).isoformat(),
        "bucket": "raw",
    }
    payload.update(overrides)
    return client.post("/api/v1/query", json=payload)


def _points(response):
    return response.json()["series"][0]["points"]


@pytest.mark.parametrize(
    ("aggregation", "expected"),
    [("avg", 25), ("min", 10), ("max", 40), ("sum", 100), ("count", 4)],
)
def test_query_aggregations(query_client: tuple[TestClient, Session, str, datetime], aggregation: str, expected: float) -> None:
    client, _db, _workspace_id, now = query_client
    response = _query(client, now, aggregation=aggregation)
    assert response.status_code == 200, response.text
    assert _points(response)[0]["value"] == expected


@pytest.mark.parametrize(
    ("aggregation", "expected"),
    [("p50", 25), ("p90", 37), ("p95", 38.5), ("p99", 39.7)],
)
def test_query_percentiles(query_client: tuple[TestClient, Session, str, datetime], aggregation: str, expected: float) -> None:
    client, _db, _workspace_id, now = query_client
    response = _query(client, now, aggregation=aggregation)
    assert response.status_code == 200, response.text
    assert _points(response)[0]["value"] == pytest.approx(expected)


def test_query_bucket_group_filter_ordering_and_limits(query_client: tuple[TestClient, Session, str, datetime]) -> None:
    client, _db, _workspace_id, now = query_client
    bucketed = _query(client, now, aggregation="avg", bucket="1m")
    assert [point["timestamp"] for point in _points(bucketed)] == [
        "2026-08-10T00:00:00",
        "2026-08-10T00:01:00",
        "2026-08-10T00:02:00",
    ]
    grouped = _query(client, now, groupBy="service")
    assert [(series["group"], series["points"][0]["value"]) for series in grouped.json()["series"]] == [("api-gateway", 15), ("auth-service", 35)]
    by_region = _query(client, now, groupBy="region")
    assert [series["group"] for series in by_region.json()["series"]] == ["us-east", "us-west"]
    filtered = _query(client, now, filters={"service": "api-gateway", "region": "us-east", "status": "healthy"})
    assert _points(filtered)[0]["value"] == 10
    limited = _query(client, now, bucket="10s", limit=2)
    body = limited.json()
    assert body["metadata"]["limited"] is True
    assert body["metadata"]["truncatedReason"] == "request_limit"
    assert body["metadata"]["returnedPoints"] == 2


def test_query_grouped_bucketed_contract(query_client: tuple[TestClient, Session, str, datetime]) -> None:
    client, _db, _workspace_id, now = query_client
    response = _query(client, now, aggregation="p95", bucket="1m", groupBy="service")
    assert response.status_code == 200, response.text
    assert [(series["group"], [point["timestamp"] for point in series["points"]]) for series in response.json()["series"]] == [
        ("api-gateway", ["2026-08-10T00:00:00"]),
        ("auth-service", ["2026-08-10T00:01:00", "2026-08-10T00:02:00"]),
    ]


def test_query_workspace_isolation_and_empty_results(query_client: tuple[TestClient, Session, str, datetime]) -> None:
    client, _db, _workspace_id, now = query_client
    response = _query(client, now, filters={"service": "leaked"})
    assert response.status_code == 200
    assert _points(response)[0]["count"] == 0
    assert _points(response)[0]["value"] is None


@pytest.mark.parametrize(
    ("aggregation", "expected"),
    [("count", 0), ("avg", None), ("min", None), ("max", None), ("sum", None), ("p95", None)],
)
def test_query_empty_raw_aggregate_contract(query_client: tuple[TestClient, Session, str, datetime], aggregation: str, expected: float | None) -> None:
    client, _db, _workspace_id, now = query_client
    response = _query(client, now, aggregation=aggregation, filters={"service": "missing"})
    assert response.status_code == 200
    point = _points(response)[0]
    assert point["count"] == 0
    assert point["value"] == expected


def test_query_empty_bucketed_and_grouped_results(query_client: tuple[TestClient, Session, str, datetime]) -> None:
    client, _db, _workspace_id, now = query_client
    assert _query(client, now, bucket="1m", filters={"service": "missing"}).json()["series"] == []
    assert _query(client, now, groupBy="service", filters={"service": "missing"}).json()["series"] == []
    assert _query(client, now, bucket="1m", groupBy="service", filters={"service": "missing"}).json()["series"] == []


def test_query_rejects_bad_input_and_unknown_fields(query_client: tuple[TestClient, Session, str, datetime]) -> None:
    client, _db, _workspace_id, now = query_client
    assert _query(client, now, metric="nope").status_code == 422
    assert _query(client, now, aggregation="median").status_code == 422
    assert _query(client, now, bucket="2m").status_code == 422
    assert _query(client, now, groupBy="host").status_code == 422
    assert _query(client, now, end=now.isoformat()).status_code == 422
    assert _query(client, now, extraField=True).status_code == 422
    assert _query(client, now, filters={"service": " api"}).status_code == 422


def test_query_range_and_group_limits(query_client: tuple[TestClient, Session, str, datetime]) -> None:
    client, db, workspace_id, now = query_client
    assert _query(client, now, end=(now + timedelta(hours=2)).isoformat()).status_code == 400
    db.add(_event("e5", workspace_id, now + timedelta(seconds=150), service="worker", latency=50))
    db.commit()
    response = _query(client, now, groupBy="service")
    assert response.json()["metadata"]["limited"] is True
    assert response.json()["metadata"]["truncatedReason"] == "max_groups"


def test_query_time_boundaries_timezone_and_window_semantics(query_client: tuple[TestClient, Session, str, datetime]) -> None:
    client, db, workspace_id, now = query_client
    db.add_all([
        _event("boundary-start", workspace_id, now + timedelta(minutes=5), latency=100),
        _event("boundary-end", workspace_id, now + timedelta(minutes=6), latency=999),
        _event("boundary-before-end", workspace_id, now + timedelta(minutes=6, microseconds=-1), latency=200),
    ])
    db.commit()
    response = _query(client, now, start=(now + timedelta(minutes=5)).isoformat(), end=(now + timedelta(minutes=6)).isoformat(), aggregation="count")
    assert _points(response)[0]["value"] == 2
    offset_start = (now + timedelta(hours=5, minutes=30)).isoformat()
    offset_end = (now + timedelta(hours=5, minutes=35)).isoformat()
    assert _query(client, now, start=offset_start, end=offset_end).status_code == 200
    assert client.post("/api/v1/query", json={"metric": "latency", "aggregation": "avg", "bucket": "raw", "windowSeconds": 60}).status_code == 200
    assert _query(client, now, windowSeconds=60).status_code == 422
    assert client.post("/api/v1/query", json={"metric": "latency", "aggregation": "avg", "bucket": "raw"}).status_code == 422


def test_query_bucket_alignment(query_client: tuple[TestClient, Session, str, datetime]) -> None:
    client, db, workspace_id, now = query_client
    db.add_all([
        _event("b10", workspace_id, now + timedelta(seconds=19), latency=10),
        _event("b1m", workspace_id, now + timedelta(seconds=37), latency=20),
        _event("b5m", workspace_id, now + timedelta(minutes=7), latency=30),
    ])
    db.commit()
    ten = _query(client, now, start=now.isoformat(), end=(now + timedelta(minutes=1)).isoformat(), bucket="10s", aggregation="count")
    assert any(point["timestamp"] == "2026-08-10T00:00:10" for point in _points(ten))
    one = _query(client, now, start=now.isoformat(), end=(now + timedelta(minutes=1)).isoformat(), bucket="1m", aggregation="count")
    assert _points(one)[0]["timestamp"] == "2026-08-10T00:00:00"
    five = _query(client, now, start=now.isoformat(), end=(now + timedelta(minutes=10)).isoformat(), bucket="5m", aggregation="count")
    assert any(point["timestamp"] == "2026-08-10T00:05:00" for point in _points(five))


def test_query_header_membership_is_authoritative(query_client: tuple[TestClient, Session, str, datetime]) -> None:
    client, db, _workspace_id, now = query_client
    user = UserModel(email="intruder@example.com", password_hash="hash")
    workspace = WorkspaceModel(name="Other", slug="other")
    db.add_all([user, workspace])
    db.flush()
    db.add(WorkspaceMembershipModel(user_id=user.id, workspace_id=workspace.id, role="owner"))
    db.commit()
    client.headers["X-Workspace-Id"] = workspace.id
    response = _query(client, now)
    assert response.status_code == 403


@pytest.mark.parametrize("role", ["owner", "admin", "member", "viewer"])
def test_query_rbac_all_workspace_roles_can_read(role: str) -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, expire_on_commit=False)()
    app.dependency_overrides[get_auth_repository] = lambda: AuthRepository(db)
    app.dependency_overrides[get_query_engine] = lambda: TelemetryQueryEngine(db)
    now = datetime(2026, 8, 10, 0, 0, tzinfo=timezone.utc)
    try:
        with TestClient(app) as client:
            workspace_id = authenticate_test_client(client, db, role=role)
            db.add(_event(f"role-{role}", workspace_id, now))
            db.commit()
            assert _query(client, now).status_code == 200
    finally:
        app.dependency_overrides.clear()
        db.close()
