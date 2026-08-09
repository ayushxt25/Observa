from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from app.schemas.metrics import MetricAggregation, MetricBucket, MetricName
from app.schemas.telemetry import ApiModel, Region, ServiceId


AlertOperator = Literal[">", ">=", "<", "<="]
AlertState = Literal["normal", "firing"]
IncidentStatus = Literal["firing", "resolved"]
MIN_EVALUATION_INTERVAL_SECONDS = 5


class AlertRuleBase(ApiModel):
    name: str = Field(min_length=1, max_length=140)
    description: str | None = Field(default=None, max_length=500)
    metric: MetricName
    service: ServiceId | None = None
    region: Region | None = None
    aggregation: MetricAggregation = "avg"
    bucket: MetricBucket = "1m"
    evaluation_window_seconds: int = Field(default=300, gt=0, le=86_400)
    operator: AlertOperator = ">="
    threshold: float = Field(ge=0)
    evaluation_interval_seconds: int = Field(default=60, ge=MIN_EVALUATION_INTERVAL_SECONDS, le=86_400)
    cooldown_seconds: int = Field(default=300, ge=0, le=86_400)
    enabled: bool = True
    notification_channel_ids: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def valid_bucket_window(self) -> "AlertRuleBase":
        if self.bucket == "1h" and self.evaluation_window_seconds < 3600:
            raise ValueError("evaluationWindowSeconds must cover at least one selected bucket")
        if self.bucket == "5m" and self.evaluation_window_seconds < 300:
            raise ValueError("evaluationWindowSeconds must cover at least one selected bucket")
        if self.bucket == "1m" and self.evaluation_window_seconds < 60:
            raise ValueError("evaluationWindowSeconds must cover at least one selected bucket")
        return self


class AlertRuleCreate(AlertRuleBase):
    pass


class AlertRulePatch(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=140)
    description: str | None = Field(default=None, max_length=500)
    metric: MetricName | None = None
    service: ServiceId | None = None
    region: Region | None = None
    aggregation: MetricAggregation | None = None
    bucket: MetricBucket | None = None
    evaluation_window_seconds: int | None = Field(default=None, gt=0, le=86_400)
    operator: AlertOperator | None = None
    threshold: float | None = Field(default=None, ge=0)
    evaluation_interval_seconds: int | None = Field(default=None, ge=MIN_EVALUATION_INTERVAL_SECONDS, le=86_400)
    cooldown_seconds: int | None = Field(default=None, ge=0, le=86_400)
    enabled: bool | None = None
    notification_channel_ids: list[str] | None = Field(default=None, max_length=20)


class AlertRuleOut(AlertRuleBase):
    id: str
    workspace_id: str
    state: AlertState
    last_evaluated_at: datetime | None
    last_triggered_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AlertListResponse(ApiModel):
    alerts: list[AlertRuleOut]


class AlertEvaluationResponse(ApiModel):
    alert: AlertRuleOut
    value: float | None
    triggered: bool
    incident_id: str | None = None


class IncidentOut(ApiModel):
    id: str
    workspace_id: str
    alert_rule_id: str
    status: IncidentStatus
    opened_at: datetime
    resolved_at: datetime | None
    triggering_value: float
    threshold: float
    message: str
    created_at: datetime
    updated_at: datetime
    rule_name: str | None = None


class IncidentListResponse(ApiModel):
    incidents: list[IncidentOut]
