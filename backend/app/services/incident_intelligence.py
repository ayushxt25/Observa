from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models.alerts import IncidentEventModel, IncidentModel
from app.models.notifications import NotificationDeliveryModel
from app.models.services import ServiceCatalogModel, ServiceDependencyModel
from app.schemas.alerts import IncidentImpactEdge, IncidentImpactResponse, IncidentImpactService, IncidentNotificationSummary, IncidentTimelineEventOut, IncidentTimelineResponse
from app.services.audit import sanitize_metadata


INCIDENT_OPENED = "incident.opened"
INCIDENT_RESOLVED = "incident.resolved"
NOTIFICATION_DELIVERED = "notification.delivered"
NOTIFICATION_FAILED = "notification.failed"


@dataclass(frozen=True)
class IncidentSnapshot:
    alert_rule_id: str
    alert_name: str | None
    metric: str | None
    threshold: float
    operator: str | None
    observed_value: float | None
    service: str | None
    region: str | None


class IncidentTimelineService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def record_opened(self, incident: IncidentModel, value: float | None, occurred_at: datetime) -> None:
        rule = incident.alert_rule
        metadata = {
            "alertRuleId": incident.alert_rule_id,
            "alertName": rule.name if rule else None,
            "metric": rule.metric if rule else None,
            "threshold": incident.threshold,
            "operator": rule.operator if rule else None,
            "observedValue": value,
            "service": rule.service if rule else None,
            "region": rule.region if rule else None,
        }
        self.record(
            workspace_id=incident.workspace_id,
            incident_id=incident.id,
            event_type=INCIDENT_OPENED,
            title="Incident opened",
            occurred_at=occurred_at,
            source_type="alert_rule",
            source_id=incident.alert_rule_id,
            actor_type="system",
            metadata=metadata,
            dedupe_key="incident.opened",
        )

    def record_resolved(self, incident: IncidentModel, value: float | None, occurred_at: datetime) -> None:
        duration = (_aware(occurred_at) - _aware(incident.opened_at)).total_seconds()
        self.record(
            workspace_id=incident.workspace_id,
            incident_id=incident.id,
            event_type=INCIDENT_RESOLVED,
            title="Incident resolved",
            occurred_at=occurred_at,
            source_type="alert_rule",
            source_id=incident.alert_rule_id,
            actor_type="system",
            metadata={"finalObservedValue": value, "durationSeconds": max(0, duration)},
            dedupe_key="incident.resolved",
        )

    def record(
        self,
        *,
        workspace_id: str,
        incident_id: str,
        event_type: str,
        title: str,
        occurred_at: datetime,
        dedupe_key: str,
        source_type: str | None = None,
        source_id: str | None = None,
        actor_type: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> IncidentEventModel | None:
        existing = self.db.scalars(
            select(IncidentEventModel).where(IncidentEventModel.incident_id == incident_id, IncidentEventModel.dedupe_key == dedupe_key)
        ).first()
        if existing is not None:
            return None
        event = IncidentEventModel(
            workspace_id=workspace_id,
            incident_id=incident_id,
            event_type=event_type,
            source_type=source_type,
            source_id=source_id,
            actor_type=actor_type,
            title=title,
            metadata_json=json.dumps(sanitize_metadata(metadata or {}), separators=(",", ":"), sort_keys=True),
            dedupe_key=dedupe_key,
            occurred_at=occurred_at,
        )
        self.db.add(event)
        self.db.flush()
        return event

    def timeline(self, workspace_id: str, incident_id: str, limit: int = 200) -> IncidentTimelineResponse:
        persisted = list(
            self.db.scalars(
                select(IncidentEventModel)
                .where(IncidentEventModel.workspace_id == workspace_id, IncidentEventModel.incident_id == incident_id)
                .order_by(IncidentEventModel.occurred_at.asc(), IncidentEventModel.id.asc())
                .limit(limit + 1)
            ).all()
        )
        events = [_event_out(event) for event in persisted] + self._delivery_events(workspace_id, incident_id, limit + 1)
        events.sort(key=lambda item: (_aware(item.occurred_at), item.id))
        limited = len(events) > limit
        if len(events) > limit:
            events = events[:limit]
        return IncidentTimelineResponse(events=events, limited=limited)

    def _delivery_events(self, workspace_id: str, incident_id: str, limit: int) -> list[IncidentTimelineEventOut]:
        rows = list(
            self.db.scalars(
                select(NotificationDeliveryModel)
                .where(
                    NotificationDeliveryModel.workspace_id == workspace_id,
                    NotificationDeliveryModel.incident_id == incident_id,
                    NotificationDeliveryModel.status.in_(["delivered", "failed"]),
                )
                .order_by(func.coalesce(NotificationDeliveryModel.delivered_at, NotificationDeliveryModel.last_attempt_at, NotificationDeliveryModel.created_at).asc(), NotificationDeliveryModel.id.asc())
                .limit(limit)
            ).all()
        )
        output: list[IncidentTimelineEventOut] = []
        for row in rows:
            event_type = NOTIFICATION_DELIVERED if row.status == "delivered" else NOTIFICATION_FAILED
            occurred = row.delivered_at or row.last_attempt_at or row.created_at
            output.append(
                IncidentTimelineEventOut(
                    id=f"delivery:{row.id}:{row.status}",
                    incident_id=incident_id,
                    event_type=event_type,
                    source_type="notification_delivery",
                    source_id=row.id,
                    actor_type="celery",
                    title=f"Notification {row.status}",
                    metadata=sanitize_metadata({
                        "channelName": row.channel_name,
                        "channelType": row.channel_type,
                        "eventType": row.event_type,
                        "attemptCount": row.attempt_count,
                        "responseCode": row.response_code,
                        "errorSummary": row.error_summary,
                    }),
                    occurred_at=occurred,
                )
            )
        return output


class IncidentImpactServiceBuilder:
    def __init__(self, db: Session) -> None:
        self.db = db

    def impact(self, incident: IncidentModel) -> IncidentImpactResponse:
        rule = incident.alert_rule
        root_name = rule.service if rule else None
        if not root_name:
            return IncidentImpactResponse(root_service=None, affected_services=[], dependency_edges=[], affected_count=0, max_depth=0, impact_unavailable=True, reason="incident_has_no_service")
        services = list(self.db.scalars(select(ServiceCatalogModel).where(ServiceCatalogModel.workspace_id == incident.workspace_id)).all())
        by_id = {service.id: service for service in services}
        root = next((service for service in services if service.name == root_name), None)
        if root is None:
            root_out = IncidentImpactService(service_id=None, name=root_name, display_name=None, depth=0, impact_status="root_cause")
            return IncidentImpactResponse(root_service=root_out, affected_services=[root_out], dependency_edges=[], affected_count=1, max_depth=0, impact_unavailable=True, reason="service_not_in_catalog")

        dependencies = list(
            self.db.scalars(
                select(ServiceDependencyModel)
                .options(joinedload(ServiceDependencyModel.source_service), joinedload(ServiceDependencyModel.target_service))
                .where(ServiceDependencyModel.workspace_id == incident.workspace_id)
            ).all()
        )
        reverse: dict[str, list[ServiceDependencyModel]] = {}
        for edge in dependencies:
            reverse.setdefault(edge.target_service_id, []).append(edge)

        depths = {root.id: 0}
        queue: deque[str] = deque([root.id])
        while queue:
            current_id = queue.popleft()
            for edge in reverse.get(current_id, []):
                next_id = edge.source_service_id
                if next_id in depths:
                    continue
                depths[next_id] = depths[current_id] + 1
                queue.append(next_id)

        affected_ids = set(depths)
        affected = [
            IncidentImpactService(
                service_id=service.id,
                name=service.name,
                display_name=service.display_name,
                depth=depths[service.id],
                impact_status="root_cause" if service.id == root.id else "affected",
            )
            for service in services
            if service.id in affected_ids
        ]
        affected.sort(key=lambda item: (item.depth, item.name))
        impact_edges = [
            IncidentImpactEdge(
                id=edge.id,
                source_service_id=edge.source_service_id,
                target_service_id=edge.target_service_id,
                source_service_name=by_id[edge.source_service_id].name,
                target_service_name=by_id[edge.target_service_id].name,
                dependency_type=edge.dependency_type,
            )
            for edge in dependencies
            if edge.source_service_id in affected_ids and edge.target_service_id in affected_ids
        ]
        impact_edges.sort(key=lambda item: (item.source_service_name, item.target_service_name, item.dependency_type, item.id))
        root_out = next(item for item in affected if item.service_id == root.id)
        return IncidentImpactResponse(
            root_service=root_out,
            affected_services=affected,
            dependency_edges=impact_edges,
            affected_count=len(affected),
            max_depth=max(depths.values()) if depths else 0,
        )


def notification_summary(db: Session, workspace_id: str, incident_id: str) -> IncidentNotificationSummary:
    rows = db.scalars(select(NotificationDeliveryModel).where(NotificationDeliveryModel.workspace_id == workspace_id, NotificationDeliveryModel.incident_id == incident_id)).all()
    counts = IncidentNotificationSummary()
    for row in rows:
        if row.status == "pending":
            counts.pending += 1
        elif row.status == "delivering":
            counts.delivering += 1
        elif row.status == "delivered":
            counts.delivered += 1
        elif row.status == "failed":
            counts.failed += 1
    return counts


def _event_out(event: IncidentEventModel) -> IncidentTimelineEventOut:
    return IncidentTimelineEventOut(
        id=event.id,
        incident_id=event.incident_id,
        event_type=event.event_type,
        source_type=event.source_type,
        source_id=event.source_id,
        actor_type=event.actor_type,
        title=event.title,
        metadata=json.loads(event.metadata_json or "{}"),
        occurred_at=event.occurred_at,
    )


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
