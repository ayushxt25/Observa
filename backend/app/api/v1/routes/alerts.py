from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.api.deps import require_workspace_role
from app.core import audit_actions
from app.db.session import get_db
from app.models.auth import WorkspaceMembershipModel
from app.repositories.alerts import AlertRepository
from app.repositories.notifications import NotificationRepository
from app.schemas.alerts import AlertEvaluationResponse, AlertListResponse, AlertRuleCreate, AlertRuleOut, AlertRulePatch, IncidentListResponse, IncidentOut, IncidentStatus
from app.services.alerts import AlertEvaluationService
from app.services.audit import AuditService, changed_fields

router = APIRouter(tags=["alerts"])


def get_alert_repository(db: Annotated[Session, Depends(get_db)]) -> AlertRepository:
    return AlertRepository(db)


def get_notification_repository(db: Annotated[Session, Depends(get_db)]) -> NotificationRepository:
    return NotificationRepository(db)


def get_alert_evaluator(db: Annotated[Session, Depends(get_db)]) -> AlertEvaluationService:
    return AlertEvaluationService(db)


def load_rule(repo: AlertRepository, rule_id: str, workspace_id: str):
    rule = repo.get_rule(rule_id, workspace_id=workspace_id)
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert rule not found")
    return rule


def incident_out(incident) -> IncidentOut:
    return IncidentOut(
        id=incident.id,
        workspace_id=incident.workspace_id,
        alert_rule_id=incident.alert_rule_id,
        status=incident.status,
        opened_at=incident.opened_at,
        resolved_at=incident.resolved_at,
        triggering_value=incident.triggering_value,
        threshold=incident.threshold,
        message=incident.message,
        created_at=incident.created_at,
        updated_at=incident.updated_at,
        rule_name=incident.alert_rule.name if incident.alert_rule else None,
    )


def alert_out(rule, notifications: NotificationRepository) -> AlertRuleOut:
    return AlertRuleOut.model_validate(rule).model_copy(update={"notification_channel_ids": notifications.alert_channel_ids(rule.workspace_id, rule.id)})


@router.get("/alerts", response_model=AlertListResponse, summary="List alert rules")
def list_alerts(repo: Annotated[AlertRepository, Depends(get_alert_repository)], notifications: Annotated[NotificationRepository, Depends(get_notification_repository)], membership: Annotated[WorkspaceMembershipModel, Depends(require_workspace_role("viewer"))]) -> AlertListResponse:
    return AlertListResponse(alerts=[alert_out(rule, notifications) for rule in repo.list_rules(membership.workspace_id)])


@router.post("/alerts", response_model=AlertRuleOut, status_code=status.HTTP_201_CREATED, summary="Create alert rule")
def create_alert(payload: AlertRuleCreate, request: Request, repo: Annotated[AlertRepository, Depends(get_alert_repository)], notifications: Annotated[NotificationRepository, Depends(get_notification_repository)], membership: Annotated[WorkspaceMembershipModel, Depends(require_workspace_role("member"))]) -> AlertRuleOut:
    rule = repo.create_rule(payload, membership.workspace_id, commit=False)
    if payload.notification_channel_ids:
        notifications.set_alert_channels(membership.workspace_id, rule.id, payload.notification_channel_ids, commit=False)
    AuditService(repo.db).record_user(membership=membership, action=audit_actions.ALERT_CREATED, resource_type="alert_rule", resource_id=rule.id, request=request, metadata={"name": rule.name, "metric": rule.metric, "enabled": rule.enabled, "notificationChannelCount": len(payload.notification_channel_ids)}, commit=False)
    repo.db.commit()
    repo.db.refresh(rule)
    return alert_out(rule, notifications)


@router.get("/alerts/{rule_id}", response_model=AlertRuleOut, summary="Get alert rule")
def get_alert(rule_id: str, repo: Annotated[AlertRepository, Depends(get_alert_repository)], notifications: Annotated[NotificationRepository, Depends(get_notification_repository)], membership: Annotated[WorkspaceMembershipModel, Depends(require_workspace_role("viewer"))]) -> AlertRuleOut:
    return alert_out(load_rule(repo, rule_id, membership.workspace_id), notifications)


@router.patch("/alerts/{rule_id}", response_model=AlertRuleOut, summary="Update alert rule")
def update_alert(rule_id: str, payload: AlertRulePatch, request: Request, repo: Annotated[AlertRepository, Depends(get_alert_repository)], notifications: Annotated[NotificationRepository, Depends(get_notification_repository)], membership: Annotated[WorkspaceMembershipModel, Depends(require_workspace_role("member"))]) -> AlertRuleOut:
    try:
        existing = load_rule(repo, rule_id, membership.workspace_id)
        before = {"name": existing.name, "metric": existing.metric, "service": existing.service, "region": existing.region, "aggregation": existing.aggregation, "bucket": existing.bucket, "operator": existing.operator, "threshold": existing.threshold, "enabled": existing.enabled}
        rule = repo.update_rule(existing, payload, commit=False)
        if payload.notification_channel_ids is not None:
            notifications.set_alert_channels(membership.workspace_id, rule.id, payload.notification_channel_ids, commit=False)
        after = {"name": rule.name, "metric": rule.metric, "service": rule.service, "region": rule.region, "aggregation": rule.aggregation, "bucket": rule.bucket, "operator": rule.operator, "threshold": rule.threshold, "enabled": rule.enabled}
        action = audit_actions.ALERT_UPDATED
        if before["enabled"] is True and after["enabled"] is False:
            action = audit_actions.ALERT_DISABLED
        elif before["enabled"] is False and after["enabled"] is True:
            action = audit_actions.ALERT_ENABLED
        AuditService(repo.db).record_user(membership=membership, action=action, resource_type="alert_rule", resource_id=rule.id, request=request, metadata=changed_fields(before, after), commit=False)
        repo.db.commit()
        repo.db.refresh(rule)
        return alert_out(rule, notifications)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.delete("/alerts/{rule_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete alert rule")
def delete_alert(rule_id: str, request: Request, repo: Annotated[AlertRepository, Depends(get_alert_repository)], membership: Annotated[WorkspaceMembershipModel, Depends(require_workspace_role("member"))]) -> None:
    try:
        rule = load_rule(repo, rule_id, membership.workspace_id)
        metadata = {"name": rule.name, "metric": rule.metric, "enabled": rule.enabled}
        repo.delete_rule(rule, commit=False)
        AuditService(repo.db).record_user(membership=membership, action=audit_actions.ALERT_DELETED, resource_type="alert_rule", resource_id=rule_id, request=request, metadata=metadata, commit=False)
        repo.db.commit()
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/alerts/{rule_id}/evaluate", response_model=AlertEvaluationResponse, summary="Evaluate alert rule now")
def evaluate_alert(rule_id: str, request: Request, repo: Annotated[AlertRepository, Depends(get_alert_repository)], evaluator: Annotated[AlertEvaluationService, Depends(get_alert_evaluator)], membership: Annotated[WorkspaceMembershipModel, Depends(require_workspace_role("member"))]) -> AlertEvaluationResponse:
    load_rule(repo, rule_id, membership.workspace_id)
    try:
        result = evaluator.evaluate_rule(rule_id)
        AuditService(repo.db).record_user(membership=membership, action=audit_actions.ALERT_MANUAL_EVALUATED, resource_type="alert_rule", resource_id=rule_id, request=request, metadata={"triggered": result.triggered, "value": result.value, "incidentId": result.incident_id})
        return result
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/incidents", response_model=IncidentListResponse, summary="List incidents")
def list_incidents(
    repo: Annotated[AlertRepository, Depends(get_alert_repository)],
    membership: Annotated[WorkspaceMembershipModel, Depends(require_workspace_role("viewer"))],
    status_filter: Annotated[IncidentStatus | None, Query(alias="status")] = None,
    alert_rule_id: str | None = None,
    service: str | None = None,
    recent_hours: Annotated[int | None, Query(ge=1, le=24 * 30)] = None,
) -> IncidentListResponse:
    return IncidentListResponse(incidents=[incident_out(incident) for incident in repo.list_incidents(status=status_filter, alert_rule_id=alert_rule_id, service=service, recent_hours=recent_hours, workspace_id=membership.workspace_id)])


@router.get("/incidents/{incident_id}", response_model=IncidentOut, summary="Get incident")
def get_incident(incident_id: str, repo: Annotated[AlertRepository, Depends(get_alert_repository)], membership: Annotated[WorkspaceMembershipModel, Depends(require_workspace_role("viewer"))]) -> IncidentOut:
    incident = repo.get_incident(incident_id, membership.workspace_id)
    if incident is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")
    return incident_out(incident)
