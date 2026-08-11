from datetime import datetime
from typing import Literal
from urllib.parse import urlparse

from pydantic import EmailStr, Field, HttpUrl, field_validator, model_validator

from app.schemas.telemetry import ApiModel


NotificationChannelType = Literal["email", "webhook"]
NotificationEventType = Literal["firing", "resolved", "test"]
NotificationDeliveryStatus = Literal["pending", "delivering", "delivered", "failed"]


class EmailChannelConfig(ApiModel):
    recipients: list[EmailStr] = Field(min_length=1, max_length=20)


class WebhookChannelConfig(ApiModel):
    target_url: HttpUrl
    label: str | None = Field(default=None, max_length=80)
    secret: str | None = Field(default=None, min_length=8, max_length=256)

    @field_validator("target_url")
    @classmethod
    def require_http_scheme(cls, value: HttpUrl) -> HttpUrl:
        parsed = urlparse(str(value))
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("webhook URL must use http or https")
        return value


class NotificationChannelCreate(ApiModel):
    name: str = Field(min_length=1, max_length=120)
    type: NotificationChannelType
    enabled: bool = True
    email_config: EmailChannelConfig | None = None
    webhook_config: WebhookChannelConfig | None = None

    @model_validator(mode="after")
    def matching_config(self) -> "NotificationChannelCreate":
        if self.type == "email" and self.email_config is None:
            raise ValueError("emailConfig is required for email channels")
        if self.type == "webhook" and self.webhook_config is None:
            raise ValueError("webhookConfig is required for webhook channels")
        return self


class NotificationChannelPatch(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    enabled: bool | None = None
    email_config: EmailChannelConfig | None = None
    webhook_config: WebhookChannelConfig | None = None


class NotificationChannelOut(ApiModel):
    id: str
    workspace_id: str
    name: str
    type: NotificationChannelType
    enabled: bool
    email_config: EmailChannelConfig | None = None
    webhook_url: str | None = None
    webhook_label: str | None = None
    has_secret: bool = False
    created_at: datetime
    updated_at: datetime


class NotificationChannelListResponse(ApiModel):
    channels: list[NotificationChannelOut]


class AlertChannelUpdate(ApiModel):
    channel_ids: list[str] = Field(default_factory=list, max_length=20)


class NotificationDeliveryOut(ApiModel):
    id: str
    workspace_id: str
    alert_rule_id: str | None
    incident_id: str | None
    channel_id: str | None
    channel_name: str
    channel_type: NotificationChannelType
    event_type: NotificationEventType
    status: NotificationDeliveryStatus
    attempt_count: int
    last_attempt_at: datetime | None
    next_retry_at: datetime | None
    response_code: int | None
    error_summary: str | None
    created_at: datetime
    delivered_at: datetime | None


class NotificationDeliveryListResponse(ApiModel):
    deliveries: list[NotificationDeliveryOut]


class TestNotificationResponse(ApiModel):
    delivery_id: str
    status: NotificationDeliveryStatus
