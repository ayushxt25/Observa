from datetime import datetime, timedelta, timezone

from typing import Literal

from pydantic import Field, field_validator, model_validator

from app.query.models import QueryAggregation, QueryBucket, QueryGroupBy, QueryMetric
from app.schemas.telemetry import ApiModel, Region, TelemetryStatus


class QueryFilters(ApiModel):
    service: str | None = Field(default=None, min_length=1, max_length=64)
    region: Region | None = None
    status: TelemetryStatus | None = None

    @field_validator("service")
    @classmethod
    def service_must_be_clean(cls, value: str | None) -> str | None:
        if value is not None and value != value.strip():
            raise ValueError("service must not include leading or trailing whitespace")
        return value


class TelemetryQueryRequest(ApiModel):
    metric: QueryMetric
    aggregation: QueryAggregation
    start: datetime | None = None
    end: datetime | None = None
    window_seconds: int | None = Field(default=None, ge=1, le=2_678_400)
    bucket: QueryBucket = "raw"
    group_by: QueryGroupBy | None = None
    filters: QueryFilters = Field(default_factory=QueryFilters)
    limit: int | None = Field(default=None, ge=1, le=10_000)

    @field_validator("start", "end")
    @classmethod
    def aware_or_none(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("query datetimes must be timezone-aware")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def validate_time_range(self) -> "TelemetryQueryRequest":
        if self.window_seconds is not None and (self.start is not None or self.end is not None):
            raise ValueError("use either windowSeconds or start/end, not both")
        if self.window_seconds is None and (self.start is None or self.end is None):
            raise ValueError("start and end are required when windowSeconds is not provided")
        if self.start is not None and self.end is not None and self.end <= self.start:
            raise ValueError("end must be after start")
        return self

    def resolved_range(self, now: datetime | None = None) -> tuple[datetime, datetime]:
        if self.window_seconds is not None:
            end = now or datetime.now(timezone.utc)
            return end - timedelta(seconds=self.window_seconds), end
        if self.start is None or self.end is None:
            raise ValueError("query time range is incomplete")
        return self.start, self.end


class QuerySeriesPoint(ApiModel):
    timestamp: datetime | None = None
    group: str | None = None
    value: float | None
    count: int = Field(ge=0)


class QueryPoint(ApiModel):
    timestamp: datetime | None = None
    value: float | None
    count: int = Field(ge=0)


class QuerySeries(ApiModel):
    group: str | None = None
    points: list[QueryPoint]


class QueryMetadata(ApiModel):
    start: datetime
    end: datetime
    execution_time_ms: float
    returned_points: int
    max_points: int
    max_groups: int
    limited: bool
    truncated_reason: str | None = None
    cache_status: Literal["hit", "miss", "bypass"] | None = None


class TelemetryQueryResponse(ApiModel):
    metric: QueryMetric
    unit: str
    aggregation: QueryAggregation
    bucket: QueryBucket
    group_by: QueryGroupBy | None = None
    filters: QueryFilters
    series: list[QuerySeries]
    metadata: QueryMetadata
