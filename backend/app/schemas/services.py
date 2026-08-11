from datetime import datetime
from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, field_validator

from app.schemas.telemetry import ApiModel, ServiceId


DependencyType = Literal["http", "queue", "database", "unknown"]
ServiceHealth = Literal["healthy", "degraded", "critical", "unknown"]


class ServiceCatalogBase(ApiModel):
    display_name: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    environment: str | None = Field(default=None, max_length=64)
    version: str | None = Field(default=None, max_length=80)
    owner_team: str | None = Field(default=None, max_length=120)
    repository_url: str | None = Field(default=None, max_length=500)
    runbook_url: str | None = Field(default=None, max_length=500)
    tags: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, value: list[str]) -> list[str]:
        normalized = []
        seen: set[str] = set()
        for item in value:
            tag = item.strip().lower()
            if not tag:
                continue
            if len(tag) > 40:
                raise ValueError("tags must be 40 characters or fewer")
            if tag in seen:
                continue
            seen.add(tag)
            normalized.append(tag)
        return normalized

    @field_validator("repository_url", "runbook_url")
    @classmethod
    def urls_must_be_http(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            return None
        parsed = urlparse(stripped)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("URL must use http or https")
        return stripped


class ServiceCatalogCreate(ServiceCatalogBase):
    name: ServiceId


class ServiceCatalogPatch(ServiceCatalogBase):
    display_name: str | None = Field(default=None, max_length=120)


class ServiceCatalogOut(ServiceCatalogBase):
    id: str
    workspace_id: str
    name: str
    last_seen_at: datetime | None
    created_at: datetime
    updated_at: datetime
    health: ServiceHealth = "unknown"
    recent_event_count: int = 0
    avg_latency: float | None = None
    error_rate: float | None = None
    throughput: float | None = None
    active_alert_count: int = 0
    active_incident_count: int = 0


class ServiceCatalogListResponse(ApiModel):
    services: list[ServiceCatalogOut]


class ServiceSummaryResponse(ServiceCatalogOut):
    pass


class ServiceDependencyCreate(ApiModel):
    source_service_id: str
    target_service_id: str
    dependency_type: DependencyType = "unknown"


class ServiceDependencyPatch(ApiModel):
    dependency_type: DependencyType | None = None


class ServiceDependencyOut(ApiModel):
    id: str
    workspace_id: str
    source_service_id: str
    target_service_id: str
    dependency_type: DependencyType
    last_seen_at: datetime | None
    created_at: datetime
    updated_at: datetime
    source_service_name: str | None = None
    target_service_name: str | None = None


class ServiceDependencyListResponse(ApiModel):
    dependencies: list[ServiceDependencyOut]
