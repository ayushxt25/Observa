from datetime import datetime

from pydantic import Field

from app.schemas.telemetry import ApiModel


class ApiKeyCreate(ApiModel):
    name: str = Field(min_length=1, max_length=120)
    expires_at: datetime | None = None


class ApiKeyOut(ApiModel):
    id: str
    workspace_id: str
    name: str
    key_prefix: str
    created_at: datetime
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None
    expires_at: datetime | None = None


class ApiKeyCreateResponse(ApiKeyOut):
    raw_key: str


class ApiKeyListResponse(ApiModel):
    api_keys: list[ApiKeyOut]
