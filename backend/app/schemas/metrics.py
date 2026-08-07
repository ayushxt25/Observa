from datetime import datetime, timezone
from typing import Literal

from pydantic import Field, field_validator

from app.schemas.telemetry import ApiModel, Region, ServiceId


MetricName = Literal["latency", "throughput", "cpuUsage", "memoryUsage", "errorRate", "payloadSize"]
MetricAggregation = Literal["avg", "min", "max", "sum", "count"]
MetricBucket = Literal["raw", "1m", "5m", "1h"]


class MetricQueryParams(ApiModel):
    start: datetime | None = None
    end: datetime | None = None
    service: ServiceId | None = None
    region: Region | None = None
    metric: MetricName = "latency"
    aggregation: MetricAggregation = "avg"
    bucket: MetricBucket = "1m"

    @field_validator("start", "end")
    @classmethod
    def aware_or_none(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("datetime query parameters must be timezone-aware")
        return value.astimezone(timezone.utc)

    def validate_range(self) -> None:
        if self.start is not None and self.end is not None and self.start >= self.end:
            raise ValueError("start must be before end")


class MetricPoint(ApiModel):
    timestamp: datetime
    value: float
    count: int = Field(ge=0)


class MetricQueryResponse(ApiModel):
    metric: MetricName
    aggregation: MetricAggregation
    bucket: MetricBucket
    points: list[MetricPoint]
    processing_duration_ms: float
    limited: bool
