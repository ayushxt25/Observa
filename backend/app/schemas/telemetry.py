from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


ServiceId = Literal["api-gateway", "auth-service", "billing-service", "search-service", "worker"]
Region = Literal["us-east", "us-west", "eu-central", "ap-south"]
TelemetryStatus = Literal["healthy", "degraded", "critical"]


def to_camel(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part.capitalize() for part in parts[1:])


class ApiModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        serialize_by_alias=True,
    )


class TelemetryEventIn(ApiModel):
    id: str = Field(min_length=1, max_length=80)
    timestamp: datetime
    service: ServiceId
    region: Region
    latency: float = Field(ge=0)
    throughput: float = Field(ge=0)
    cpu_usage: float = Field(ge=0, le=100)
    memory_usage: float = Field(ge=0, le=100)
    error_rate: float = Field(ge=0, le=100)
    payload_size: int = Field(ge=0)
    status: TelemetryStatus

    @field_validator("timestamp")
    @classmethod
    def timestamp_must_be_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")
        return value.astimezone(timezone.utc)


class TelemetryBatchIn(ApiModel):
    events: list[TelemetryEventIn] = Field(min_length=1)


class IngestionResponse(ApiModel):
    accepted_count: int
    rejected_count: int = 0
    processing_duration_ms: float


class ServiceSummary(ApiModel):
    service: str
    latest_timestamp: datetime | None
    recent_event_count: int


class ServicesResponse(ApiModel):
    services: list[ServiceSummary]
