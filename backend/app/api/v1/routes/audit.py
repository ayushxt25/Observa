import json
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import require_workspace_role
from app.db.session import get_db
from app.models.auth import WorkspaceMembershipModel
from app.repositories.audit import AuditRepository
from app.schemas.audit import AuditActorType, AuditEventFilters, AuditEventListResponse, AuditEventOut, AuditOutcome

router = APIRouter(prefix="/audit-events", tags=["audit"])


def get_audit_repository(db: Annotated[Session, Depends(get_db)]) -> AuditRepository:
    return AuditRepository(db)


def audit_out(event) -> AuditEventOut:
    return AuditEventOut(
        id=event.id,
        workspace_id=event.workspace_id,
        actor_user_id=event.actor_user_id,
        actor_type=event.actor_type,
        action=event.action,
        resource_type=event.resource_type,
        resource_id=event.resource_id,
        outcome=event.outcome,
        ip_address=event.ip_address,
        user_agent=event.user_agent,
        request_id=event.request_id,
        metadata=json.loads(event.metadata_json),
        created_at=event.created_at,
    )


@router.get("", response_model=AuditEventListResponse, summary="List audit events")
def list_audit_events(
    repo: Annotated[AuditRepository, Depends(get_audit_repository)],
    membership: Annotated[WorkspaceMembershipModel, Depends(require_workspace_role("admin"))],
    actor_user_id: Annotated[str | None, Query(alias="actorUserId")] = None,
    actor_type: Annotated[AuditActorType | None, Query(alias="actorType")] = None,
    action: str | None = None,
    resource_type: Annotated[str | None, Query(alias="resourceType")] = None,
    resource_id: Annotated[str | None, Query(alias="resourceId")] = None,
    outcome: AuditOutcome | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> AuditEventListResponse:
    filters = AuditEventFilters(
        actor_user_id=actor_user_id,
        actor_type=actor_type,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        outcome=outcome,
        start=start,
        end=end,
        cursor=cursor,
        limit=limit,
    )
    try:
        rows, next_cursor = repo.list(membership.workspace_id, filters)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return AuditEventListResponse(events=[audit_out(row) for row in rows], next_cursor=next_cursor)


@router.get("/{event_id}", response_model=AuditEventOut, summary="Get audit event")
def get_audit_event(
    event_id: str,
    repo: Annotated[AuditRepository, Depends(get_audit_repository)],
    membership: Annotated[WorkspaceMembershipModel, Depends(require_workspace_role("admin"))],
) -> AuditEventOut:
    event = repo.get(membership.workspace_id, event_id)
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audit event not found")
    return audit_out(event)
