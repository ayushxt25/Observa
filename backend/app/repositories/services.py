from __future__ import annotations

from datetime import datetime, timezone
import json

from sqlalchemy import and_, func, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.models.alerts import AlertRuleModel, IncidentModel
from app.models.services import ServiceCatalogModel, ServiceDependencyModel
from app.query.engine import TelemetryQueryEngine
from app.query.models import TelemetrySummary
from app.schemas.services import (
    ServiceCatalogCreate,
    ServiceCatalogOut,
    ServiceCatalogPatch,
    ServiceDependencyCreate,
    ServiceDependencyOut,
    ServiceDependencyPatch,
    ServiceHealth,
)


class ServiceCatalogRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list(self, workspace_id: str) -> list[ServiceCatalogModel]:
        stmt = select(ServiceCatalogModel).where(ServiceCatalogModel.workspace_id == workspace_id).order_by(ServiceCatalogModel.name)
        return list(self.db.scalars(stmt).all())

    def get(self, service_id: str, workspace_id: str) -> ServiceCatalogModel | None:
        stmt = select(ServiceCatalogModel).where(ServiceCatalogModel.id == service_id, ServiceCatalogModel.workspace_id == workspace_id)
        return self.db.scalars(stmt).first()

    def get_by_name(self, workspace_id: str, name: str) -> ServiceCatalogModel | None:
        stmt = select(ServiceCatalogModel).where(ServiceCatalogModel.workspace_id == workspace_id, ServiceCatalogModel.name == name)
        return self.db.scalars(stmt).first()

    def create(self, payload: ServiceCatalogCreate, workspace_id: str, *, commit: bool = True) -> ServiceCatalogModel:
        service = ServiceCatalogModel(
            workspace_id=workspace_id,
            name=payload.name,
            display_name=payload.display_name,
            description=payload.description,
            environment=payload.environment,
            version=payload.version,
            owner_team=payload.owner_team,
            repository_url=payload.repository_url,
            runbook_url=payload.runbook_url,
            tags_json=json.dumps(payload.tags),
        )
        self.db.add(service)
        try:
            if commit:
                self.db.commit()
                self.db.refresh(service)
            else:
                self.db.flush()
        except IntegrityError as exc:
            self.db.rollback()
            raise ValueError("Service already exists") from exc
        return service

    def update(self, service: ServiceCatalogModel, payload: ServiceCatalogPatch, *, commit: bool = True) -> ServiceCatalogModel:
        data = payload.model_dump(exclude_unset=True)
        if "tags" in data:
            service.tags_json = json.dumps(data.pop("tags"))
        for key, value in data.items():
            setattr(service, key, value)
        if commit:
            self.db.commit()
            self.db.refresh(service)
        else:
            self.db.flush()
        return service

    def delete(self, service: ServiceCatalogModel, *, commit: bool = True) -> None:
        self.db.delete(service)
        if commit:
            self.db.commit()
        else:
            self.db.flush()

    def upsert_observed(self, workspace_id: str, observed: dict[str, datetime]) -> None:
        if not observed:
            return
        if self.db.get_bind().dialect.name == "postgresql":
            rows = [
                {"workspace_id": workspace_id, "name": name, "last_seen_at": timestamp, "tags_json": "[]"}
                for name, timestamp in observed.items()
            ]
            stmt = postgresql_insert(ServiceCatalogModel).values(rows)
            self.db.execute(
                stmt.on_conflict_do_update(
                    constraint="uq_services_workspace_name",
                    set_={
                        "last_seen_at": func.greatest(
                            func.coalesce(ServiceCatalogModel.last_seen_at, stmt.excluded.last_seen_at),
                            stmt.excluded.last_seen_at,
                        )
                    },
                )
            )
            self.db.flush()
            return
        names = list(observed)
        existing = {
            service.name: service
            for service in self.db.scalars(
                select(ServiceCatalogModel).where(ServiceCatalogModel.workspace_id == workspace_id, ServiceCatalogModel.name.in_(names))
            ).all()
        }
        for name, timestamp in observed.items():
            current = existing.get(name)
            if current is None:
                self.db.add(ServiceCatalogModel(workspace_id=workspace_id, name=name, last_seen_at=timestamp, tags_json="[]"))
            elif current.last_seen_at is None or _aware(current.last_seen_at) < _aware(timestamp):
                current.last_seen_at = timestamp
        self.db.flush()

    def list_dependencies(self, workspace_id: str) -> list[ServiceDependencyModel]:
        stmt = (
            select(ServiceDependencyModel)
            .options(joinedload(ServiceDependencyModel.source_service), joinedload(ServiceDependencyModel.target_service))
            .where(ServiceDependencyModel.workspace_id == workspace_id)
            .order_by(ServiceDependencyModel.created_at.desc())
        )
        return list(self.db.scalars(stmt).all())

    def get_dependency(self, dependency_id: str, workspace_id: str) -> ServiceDependencyModel | None:
        stmt = (
            select(ServiceDependencyModel)
            .options(joinedload(ServiceDependencyModel.source_service), joinedload(ServiceDependencyModel.target_service))
            .where(ServiceDependencyModel.id == dependency_id, ServiceDependencyModel.workspace_id == workspace_id)
        )
        return self.db.scalars(stmt).first()

    def create_dependency(self, payload: ServiceDependencyCreate, workspace_id: str, *, commit: bool = True) -> ServiceDependencyModel:
        self._validate_dependency_services(payload.source_service_id, payload.target_service_id, workspace_id)
        dependency = ServiceDependencyModel(
            workspace_id=workspace_id,
            source_service_id=payload.source_service_id,
            target_service_id=payload.target_service_id,
            dependency_type=payload.dependency_type,
        )
        self.db.add(dependency)
        try:
            if commit:
                self.db.commit()
                self.db.refresh(dependency)
            else:
                self.db.flush()
        except IntegrityError as exc:
            self.db.rollback()
            raise ValueError("Dependency already exists") from exc
        return dependency

    def update_dependency(self, dependency: ServiceDependencyModel, payload: ServiceDependencyPatch, *, commit: bool = True) -> ServiceDependencyModel:
        data = payload.model_dump(exclude_unset=True)
        for key, value in data.items():
            setattr(dependency, key, value)
        try:
            if commit:
                self.db.commit()
                self.db.refresh(dependency)
            else:
                self.db.flush()
        except IntegrityError as exc:
            self.db.rollback()
            raise ValueError("Dependency already exists") from exc
        return dependency

    def delete_dependency(self, dependency: ServiceDependencyModel, *, commit: bool = True) -> None:
        self.db.delete(dependency)
        if commit:
            self.db.commit()
        else:
            self.db.flush()

    def to_out(self, service: ServiceCatalogModel, summary: dict[str, object] | None = None) -> ServiceCatalogOut:
        resolved_summary = summary or self._summary_metrics(service.workspace_id, service.name)
        return ServiceCatalogOut(
            id=service.id,
            workspace_id=service.workspace_id,
            name=service.name,
            display_name=service.display_name,
            description=service.description,
            environment=service.environment,
            version=service.version,
            owner_team=service.owner_team,
            repository_url=service.repository_url,
            runbook_url=service.runbook_url,
            tags=json.loads(service.tags_json or "[]"),
            last_seen_at=service.last_seen_at,
            created_at=service.created_at,
            updated_at=service.updated_at,
            **resolved_summary,
        )

    def summary_map(self, workspace_id: str, service_names: list[str]) -> dict[str, dict[str, object]]:
        if not service_names:
            return {}
        end = datetime.now(timezone.utc)
        telemetry = TelemetryQueryEngine(self.db).service_summary_map(workspace_id, service_names, end=end)
        alert_rows = self.db.execute(
            select(AlertRuleModel.service, func.count(AlertRuleModel.id))
            .where(
                AlertRuleModel.workspace_id == workspace_id,
                AlertRuleModel.service.in_(service_names),
                AlertRuleModel.state == "firing",
                AlertRuleModel.enabled.is_(True),
            )
            .group_by(AlertRuleModel.service)
        ).all()
        incident_rows = self.db.execute(
            select(AlertRuleModel.service, func.count(IncidentModel.id))
            .join(AlertRuleModel, AlertRuleModel.id == IncidentModel.alert_rule_id)
            .where(
                IncidentModel.workspace_id == workspace_id,
                IncidentModel.status == "firing",
                AlertRuleModel.service.in_(service_names),
            )
            .group_by(AlertRuleModel.service)
        ).all()
        alerts = {row[0]: int(row[1] or 0) for row in alert_rows if row[0] is not None}
        incidents = {row[0]: int(row[1] or 0) for row in incident_rows if row[0] is not None}
        return {
            name: self._summary_from_values(
                telemetry.get(name, TelemetrySummary(0, None, None, None)),
                alerts.get(name, 0),
                incidents.get(name, 0),
            )
            for name in service_names
        }

    def dependency_to_out(self, dependency: ServiceDependencyModel) -> ServiceDependencyOut:
        return ServiceDependencyOut(
            id=dependency.id,
            workspace_id=dependency.workspace_id,
            source_service_id=dependency.source_service_id,
            target_service_id=dependency.target_service_id,
            dependency_type=dependency.dependency_type,
            last_seen_at=dependency.last_seen_at,
            created_at=dependency.created_at,
            updated_at=dependency.updated_at,
            source_service_name=dependency.source_service.name if dependency.source_service else None,
            target_service_name=dependency.target_service.name if dependency.target_service else None,
        )

    def _validate_dependency_services(self, source_id: str, target_id: str, workspace_id: str) -> None:
        if source_id == target_id:
            raise ValueError("Dependency source and target must differ")
        count = self.db.scalar(
            select(func.count(ServiceCatalogModel.id)).where(
                ServiceCatalogModel.workspace_id == workspace_id,
                ServiceCatalogModel.id.in_([source_id, target_id]),
            )
        )
        if count != 2:
            raise ValueError("Dependency services must belong to the active workspace")

    def _summary_metrics(self, workspace_id: str, service_name: str) -> dict[str, object]:
        end = datetime.now(timezone.utc)
        telemetry = TelemetryQueryEngine(self.db).service_summary(workspace_id, service_name, end=end)
        active_alerts = self.db.scalar(
            select(func.count(AlertRuleModel.id)).where(
                AlertRuleModel.workspace_id == workspace_id,
                AlertRuleModel.service == service_name,
                AlertRuleModel.state == "firing",
                AlertRuleModel.enabled.is_(True),
            )
        ) or 0
        active_incidents = self.db.scalar(
            select(func.count(IncidentModel.id))
            .join(AlertRuleModel, AlertRuleModel.id == IncidentModel.alert_rule_id)
            .where(
                IncidentModel.workspace_id == workspace_id,
                IncidentModel.status == "firing",
                AlertRuleModel.service == service_name,
            )
        ) or 0
        return self._summary_from_values(telemetry, int(active_alerts), int(active_incidents))

    def _summary_from_values(
        self,
        telemetry: TelemetrySummary,
        active_alerts: int,
        active_incidents: int,
    ) -> dict[str, object]:
        health = self._health(telemetry.event_count, telemetry.avg_latency, telemetry.avg_error_rate, active_alerts, active_incidents)
        return {
            "health": health,
            "recent_event_count": telemetry.event_count,
            "avg_latency": telemetry.avg_latency,
            "error_rate": telemetry.avg_error_rate,
            "throughput": telemetry.avg_throughput,
            "active_alert_count": active_alerts,
            "active_incident_count": active_incidents,
        }

    def _health(self, count: int, avg_latency: float | None, error_rate: float | None, active_alerts: int, active_incidents: int) -> ServiceHealth:
        if count == 0 and active_alerts == 0 and active_incidents == 0:
            return "unknown"
        if active_incidents > 0 or (error_rate is not None and error_rate >= 5) or (avg_latency is not None and avg_latency >= 500):
            return "critical"
        if active_alerts > 0 or (error_rate is not None and error_rate >= 1) or (avg_latency is not None and avg_latency >= 250):
            return "degraded"
        return "healthy"


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
