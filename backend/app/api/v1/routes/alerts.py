from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories.alerts import AlertRepository
from app.schemas.alerts import (
    AlertEvaluationResponse,
    AlertListResponse,
    AlertRuleCreate,
    AlertRuleOut,
    AlertRulePatch,
    IncidentListResponse,
    IncidentOut,
    IncidentStatus,
)
from app.services.alerts import AlertEvaluationService

router = APIRouter(tags=["alerts"])


def get_alert_repository(db: Annotated[Session, Depends(get_db)]) -> AlertRepository:
    return AlertRepository(db)


def get_alert_evaluator(db: Annotated[Session, Depends(get_db)]) -> AlertEvaluationService:
    return AlertEvaluationService(db)


def load_rule(repo: AlertRepository, rule_id: str):
    rule = repo.get_rule(rule_id)
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert rule not found")
    return rule


def incident_out(incident) -> IncidentOut:
    return IncidentOut(
        id=incident.id,
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


@router.get("/alerts", response_model=AlertListResponse, summary="List alert rules")
def list_alerts(repo: Annotated[AlertRepository, Depends(get_alert_repository)]) -> AlertListResponse:
    return AlertListResponse(alerts=repo.list_rules())


@router.post("/alerts", response_model=AlertRuleOut, status_code=status.HTTP_201_CREATED, summary="Create alert rule")
def create_alert(payload: AlertRuleCreate, repo: Annotated[AlertRepository, Depends(get_alert_repository)]) -> AlertRuleOut:
    return repo.create_rule(payload)


@router.get("/alerts/{rule_id}", response_model=AlertRuleOut, summary="Get alert rule")
def get_alert(rule_id: str, repo: Annotated[AlertRepository, Depends(get_alert_repository)]) -> AlertRuleOut:
    return load_rule(repo, rule_id)


@router.patch("/alerts/{rule_id}", response_model=AlertRuleOut, summary="Update alert rule")
def update_alert(rule_id: str, payload: AlertRulePatch, repo: Annotated[AlertRepository, Depends(get_alert_repository)]) -> AlertRuleOut:
    try:
        return repo.update_rule(load_rule(repo, rule_id), payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.delete("/alerts/{rule_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete alert rule")
def delete_alert(rule_id: str, repo: Annotated[AlertRepository, Depends(get_alert_repository)]) -> None:
    try:
        repo.delete_rule(load_rule(repo, rule_id))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/alerts/{rule_id}/evaluate", response_model=AlertEvaluationResponse, summary="Evaluate alert rule now")
def evaluate_alert(rule_id: str, evaluator: Annotated[AlertEvaluationService, Depends(get_alert_evaluator)]) -> AlertEvaluationResponse:
    try:
        return evaluator.evaluate_rule(rule_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/incidents", response_model=IncidentListResponse, summary="List incidents")
def list_incidents(
    repo: Annotated[AlertRepository, Depends(get_alert_repository)],
    status_filter: Annotated[IncidentStatus | None, Query(alias="status")] = None,
    alert_rule_id: str | None = None,
    service: str | None = None,
    recent_hours: Annotated[int | None, Query(ge=1, le=24 * 30)] = None,
) -> IncidentListResponse:
    return IncidentListResponse(incidents=[incident_out(incident) for incident in repo.list_incidents(status=status_filter, alert_rule_id=alert_rule_id, service=service, recent_hours=recent_hours)])


@router.get("/incidents/{incident_id}", response_model=IncidentOut, summary="Get incident")
def get_incident(incident_id: str, repo: Annotated[AlertRepository, Depends(get_alert_repository)]) -> IncidentOut:
    incident = repo.get_incident(incident_id)
    if incident is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")
    return incident_out(incident)
