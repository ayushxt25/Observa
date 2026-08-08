from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from app.schemas.metrics import MetricBucket, MetricName
from app.schemas.telemetry import ApiModel, Region, ServiceId


WidgetType = Literal["line", "bar", "scatter", "heatmap", "stat"]
WidgetAggregation = Literal["raw", "avg", "min", "max", "sum", "count"]
WidgetTimeRange = Literal["5m", "15m", "1h", "6h", "all"]


class DashboardWidgetBase(ApiModel):
    title: str = Field(min_length=1, max_length=160)
    type: WidgetType
    metric: MetricName = "latency"
    service: ServiceId | None = None
    region: Region | None = None
    aggregation: WidgetAggregation = "avg"
    bucket: MetricBucket = "1m"
    time_range: WidgetTimeRange = "15m"
    position: int = Field(default=0, ge=0)
    width: int = Field(default=1, ge=1, le=2)
    height: int = Field(default=1, ge=1, le=2)
    threshold_warning: float | None = Field(default=None, ge=0)
    threshold_critical: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def thresholds_in_order(self) -> "DashboardWidgetBase":
        if (
            self.threshold_warning is not None
            and self.threshold_critical is not None
            and self.threshold_warning > self.threshold_critical
        ):
            raise ValueError("thresholdWarning must be less than or equal to thresholdCritical")
        return self


class DashboardWidgetCreate(DashboardWidgetBase):
    pass


class DashboardWidgetPatch(ApiModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    type: WidgetType | None = None
    metric: MetricName | None = None
    service: ServiceId | None = None
    region: Region | None = None
    aggregation: WidgetAggregation | None = None
    bucket: MetricBucket | None = None
    time_range: WidgetTimeRange | None = None
    position: int | None = Field(default=None, ge=0)
    width: int | None = Field(default=None, ge=1, le=2)
    height: int | None = Field(default=None, ge=1, le=2)
    threshold_warning: float | None = Field(default=None, ge=0)
    threshold_critical: float | None = Field(default=None, ge=0)


class DashboardWidgetOut(DashboardWidgetBase):
    id: str
    dashboard_id: str
    created_at: datetime
    updated_at: datetime


class DashboardBase(ApiModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)


class DashboardCreate(DashboardBase):
    widgets: list[DashboardWidgetCreate] = Field(default_factory=list)


class DashboardPatch(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)


class DashboardOut(DashboardBase):
    id: str
    created_at: datetime
    updated_at: datetime
    widgets: list[DashboardWidgetOut] = Field(default_factory=list)


class DashboardListResponse(ApiModel):
    dashboards: list[DashboardOut]
