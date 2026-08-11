from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.schemas.metrics import MetricQueryParams
from app.schemas.telemetry import TelemetryEventIn


def valid_event() -> dict[str, object]:
    return {
        "id": "event-1",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": "api-gateway",
        "region": "us-east",
        "latency": 120.5,
        "throughput": 900.0,
        "cpuUsage": 52.0,
        "memoryUsage": 61.0,
        "errorRate": 0.4,
        "payloadSize": 2048,
        "status": "healthy",
    }


def test_telemetry_event_accepts_camel_case() -> None:
    event = TelemetryEventIn.model_validate(valid_event())
    assert event.cpu_usage == 52.0
    assert event.timestamp.tzinfo is not None


def test_invalid_percentage_is_rejected() -> None:
    payload = valid_event()
    payload["cpuUsage"] = 130
    with pytest.raises(ValidationError):
        TelemetryEventIn.model_validate(payload)


def test_invalid_metric_range_is_rejected() -> None:
    params = MetricQueryParams(
        start=datetime(2026, 8, 7, 12, tzinfo=timezone.utc),
        end=datetime(2026, 8, 7, 11, tzinfo=timezone.utc),
    )
    with pytest.raises(ValueError):
        params.validate_range()


def test_production_rejects_development_security_defaults() -> None:
    with pytest.raises(ValidationError):
        Settings(app_env="production")


def test_production_accepts_explicit_security_configuration() -> None:
    settings = Settings(
        app_env="production",
        jwt_secret_key="x" * 40,
        notification_secret_key="y" * 40,
        cookie_secure=True,
        cors_origins="https://observa.example.com",
        webhook_allow_private_networks=False,
    )
    assert settings.allowed_origins == ["https://observa.example.com"]


def test_production_rejects_wildcard_cors_and_private_webhooks() -> None:
    secure = {
        "app_env": "production",
        "jwt_secret_key": "x" * 40,
        "notification_secret_key": "y" * 40,
        "cookie_secure": True,
    }
    with pytest.raises(ValidationError):
        Settings(**secure, cors_origins="*")
    with pytest.raises(ValidationError):
        Settings(**secure, cors_origins="https://observa.example.com", webhook_allow_private_networks=True)
