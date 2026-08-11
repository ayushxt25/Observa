from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import require_workspace_role
from app.core import audit_actions
from app.db.session import get_db
from app.models.auth import WorkspaceMembershipModel
from app.repositories.dashboards import DashboardRepository
from app.schemas.dashboards import (
    DashboardCreate,
    DashboardListResponse,
    DashboardOut,
    DashboardPatch,
    DashboardWidgetCreate,
    DashboardWidgetOut,
    DashboardWidgetPatch,
)
from app.services.audit import AuditService, changed_fields

router = APIRouter(prefix="/dashboards", tags=["dashboards"])


def get_dashboard_repository(db: Annotated[Session, Depends(get_db)]) -> DashboardRepository:
    return DashboardRepository(db)


def load_dashboard(repo: DashboardRepository, dashboard_id: str, workspace_id: str):
    dashboard = repo.get(dashboard_id, workspace_id)
    if dashboard is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dashboard not found")
    return dashboard


@router.get("", response_model=DashboardListResponse, summary="List saved dashboards")
def list_dashboards(
    repo: Annotated[DashboardRepository, Depends(get_dashboard_repository)],
    membership: Annotated[WorkspaceMembershipModel, Depends(require_workspace_role("viewer"))],
) -> DashboardListResponse:
    return DashboardListResponse(dashboards=repo.list(membership.workspace_id))


@router.post("", response_model=DashboardOut, status_code=status.HTTP_201_CREATED, summary="Create a dashboard")
def create_dashboard(
    payload: DashboardCreate,
    request: Request,
    repo: Annotated[DashboardRepository, Depends(get_dashboard_repository)],
    membership: Annotated[WorkspaceMembershipModel, Depends(require_workspace_role("member"))],
) -> DashboardOut:
    dashboard = repo.create(payload, membership.workspace_id, commit=False)
    AuditService(repo.db).record_user(membership=membership, action=audit_actions.DASHBOARD_CREATED, resource_type="dashboard", resource_id=dashboard.id, request=request, metadata={"name": dashboard.name, "widgetCount": len(dashboard.widgets)}, commit=False)
    repo.db.commit()
    repo.db.refresh(dashboard)
    return dashboard


@router.get("/{dashboard_id}", response_model=DashboardOut, summary="Get a dashboard")
def get_dashboard(
    dashboard_id: str,
    repo: Annotated[DashboardRepository, Depends(get_dashboard_repository)],
    membership: Annotated[WorkspaceMembershipModel, Depends(require_workspace_role("viewer"))],
) -> DashboardOut:
    return load_dashboard(repo, dashboard_id, membership.workspace_id)


@router.patch("/{dashboard_id}", response_model=DashboardOut, summary="Update a dashboard")
def update_dashboard(
    dashboard_id: str,
    payload: DashboardPatch,
    request: Request,
    repo: Annotated[DashboardRepository, Depends(get_dashboard_repository)],
    membership: Annotated[WorkspaceMembershipModel, Depends(require_workspace_role("member"))],
) -> DashboardOut:
    dashboard = load_dashboard(repo, dashboard_id, membership.workspace_id)
    before = {"name": dashboard.name, "description": dashboard.description}
    updated = repo.update(dashboard, payload, commit=False)
    AuditService(repo.db).record_user(membership=membership, action=audit_actions.DASHBOARD_UPDATED, resource_type="dashboard", resource_id=dashboard_id, request=request, metadata=changed_fields(before, {"name": updated.name, "description": updated.description}), commit=False)
    repo.db.commit()
    repo.db.refresh(updated)
    return updated


@router.delete("/{dashboard_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a dashboard")
def delete_dashboard(
    dashboard_id: str,
    request: Request,
    repo: Annotated[DashboardRepository, Depends(get_dashboard_repository)],
    membership: Annotated[WorkspaceMembershipModel, Depends(require_workspace_role("member"))],
) -> None:
    dashboard = load_dashboard(repo, dashboard_id, membership.workspace_id)
    metadata = {"name": dashboard.name, "widgetCount": len(dashboard.widgets)}
    repo.delete(dashboard, commit=False)
    AuditService(repo.db).record_user(membership=membership, action=audit_actions.DASHBOARD_DELETED, resource_type="dashboard", resource_id=dashboard_id, request=request, metadata=metadata, commit=False)
    repo.db.commit()


@router.post("/{dashboard_id}/widgets", response_model=DashboardWidgetOut, status_code=status.HTTP_201_CREATED, summary="Create a widget")
def create_widget(
    dashboard_id: str,
    payload: DashboardWidgetCreate,
    request: Request,
    repo: Annotated[DashboardRepository, Depends(get_dashboard_repository)],
    membership: Annotated[WorkspaceMembershipModel, Depends(require_workspace_role("member"))],
) -> DashboardWidgetOut:
    widget = repo.create_widget(load_dashboard(repo, dashboard_id, membership.workspace_id), payload, commit=False)
    AuditService(repo.db).record_user(membership=membership, action=audit_actions.WIDGET_CREATED, resource_type="dashboard_widget", resource_id=widget.id, request=request, metadata={"dashboardId": dashboard_id, "title": widget.title, "type": widget.type, "metric": widget.metric, "position": widget.position}, commit=False)
    repo.db.commit()
    repo.db.refresh(widget)
    return widget


@router.patch("/{dashboard_id}/widgets/{widget_id}", response_model=DashboardWidgetOut, summary="Update a widget")
def update_widget(
    dashboard_id: str,
    widget_id: str,
    payload: DashboardWidgetPatch,
    request: Request,
    repo: Annotated[DashboardRepository, Depends(get_dashboard_repository)],
    membership: Annotated[WorkspaceMembershipModel, Depends(require_workspace_role("member"))],
) -> DashboardWidgetOut:
    load_dashboard(repo, dashboard_id, membership.workspace_id)
    widget = repo.get_widget(dashboard_id, widget_id)
    if widget is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Widget not found")
    try:
        before = {"title": widget.title, "type": widget.type, "metric": widget.metric, "service": widget.service, "region": widget.region, "aggregation": widget.aggregation, "bucket": widget.bucket, "timeRange": widget.time_range, "position": widget.position, "thresholdWarning": widget.threshold_warning, "thresholdCritical": widget.threshold_critical}
        updated = repo.update_widget(widget, payload, commit=False)
        after = {"title": updated.title, "type": updated.type, "metric": updated.metric, "service": updated.service, "region": updated.region, "aggregation": updated.aggregation, "bucket": updated.bucket, "timeRange": updated.time_range, "position": updated.position, "thresholdWarning": updated.threshold_warning, "thresholdCritical": updated.threshold_critical}
        AuditService(repo.db).record_user(membership=membership, action=audit_actions.WIDGET_UPDATED, resource_type="dashboard_widget", resource_id=widget_id, request=request, metadata={"dashboardId": dashboard_id, **changed_fields(before, after)}, commit=False)
        repo.db.commit()
        repo.db.refresh(updated)
        return updated
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.delete("/{dashboard_id}/widgets/{widget_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a widget")
def delete_widget(
    dashboard_id: str,
    widget_id: str,
    request: Request,
    repo: Annotated[DashboardRepository, Depends(get_dashboard_repository)],
    membership: Annotated[WorkspaceMembershipModel, Depends(require_workspace_role("member"))],
) -> None:
    load_dashboard(repo, dashboard_id, membership.workspace_id)
    widget = repo.get_widget(dashboard_id, widget_id)
    if widget is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Widget not found")
    metadata = {"dashboardId": dashboard_id, "title": widget.title, "type": widget.type, "metric": widget.metric, "position": widget.position}
    repo.delete_widget(widget, commit=False)
    AuditService(repo.db).record_user(membership=membership, action=audit_actions.WIDGET_DELETED, resource_type="dashboard_widget", resource_id=widget_id, request=request, metadata=metadata, commit=False)
    repo.db.commit()
