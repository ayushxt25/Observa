from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from app.schemas.telemetry import ApiModel


AuditActorType = Literal["user", "api_key", "system", "celery"]
AuditOutcome = Literal["success", "failure"]


class AuditEventOut(ApiModel):
    id: str
    workspace_id: str
    actor_user_id: str | None
    actor_type: AuditActorType
    action: str
    resource_type: str
    resource_id: str | None
    outcome: AuditOutcome
    ip_address: str | None
    user_agent: str | None
    request_id: str | None
    metadata: dict[str, Any]
    created_at: datetime


class AuditEventListResponse(ApiModel):
    events: list[AuditEventOut]
    next_cursor: str | None = None


class AuditEventFilters(ApiModel):
    actor_user_id: str | None = None
    actor_type: AuditActorType | None = None
    action: str | None = Field(default=None, max_length=80)
    resource_type: str | None = Field(default=None, max_length=80)
    resource_id: str | None = Field(default=None, max_length=80)
    outcome: AuditOutcome | None = None
    start: datetime | None = None
    end: datetime | None = None
    cursor: str | None = None
    limit: int = Field(default=50, ge=1, le=200)
