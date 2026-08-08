from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
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

router = APIRouter(prefix="/dashboards", tags=["dashboards"])


def get_dashboard_repository(db: Annotated[Session, Depends(get_db)]) -> DashboardRepository:
    return DashboardRepository(db)


def load_dashboard(repo: DashboardRepository, dashboard_id: str):
    dashboard = repo.get(dashboard_id)
    if dashboard is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dashboard not found")
    return dashboard


@router.get("", response_model=DashboardListResponse, summary="List saved dashboards")
def list_dashboards(repo: Annotated[DashboardRepository, Depends(get_dashboard_repository)]) -> DashboardListResponse:
    return DashboardListResponse(dashboards=repo.list())


@router.post("", response_model=DashboardOut, status_code=status.HTTP_201_CREATED, summary="Create a dashboard")
def create_dashboard(
    payload: DashboardCreate,
    repo: Annotated[DashboardRepository, Depends(get_dashboard_repository)],
) -> DashboardOut:
    return repo.create(payload)


@router.get("/{dashboard_id}", response_model=DashboardOut, summary="Get a dashboard")
def get_dashboard(
    dashboard_id: str,
    repo: Annotated[DashboardRepository, Depends(get_dashboard_repository)],
) -> DashboardOut:
    return load_dashboard(repo, dashboard_id)


@router.patch("/{dashboard_id}", response_model=DashboardOut, summary="Update a dashboard")
def update_dashboard(
    dashboard_id: str,
    payload: DashboardPatch,
    repo: Annotated[DashboardRepository, Depends(get_dashboard_repository)],
) -> DashboardOut:
    return repo.update(load_dashboard(repo, dashboard_id), payload)


@router.delete("/{dashboard_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a dashboard")
def delete_dashboard(
    dashboard_id: str,
    repo: Annotated[DashboardRepository, Depends(get_dashboard_repository)],
) -> None:
    repo.delete(load_dashboard(repo, dashboard_id))


@router.post("/{dashboard_id}/widgets", response_model=DashboardWidgetOut, status_code=status.HTTP_201_CREATED, summary="Create a widget")
def create_widget(
    dashboard_id: str,
    payload: DashboardWidgetCreate,
    repo: Annotated[DashboardRepository, Depends(get_dashboard_repository)],
) -> DashboardWidgetOut:
    return repo.create_widget(load_dashboard(repo, dashboard_id), payload)


@router.patch("/{dashboard_id}/widgets/{widget_id}", response_model=DashboardWidgetOut, summary="Update a widget")
def update_widget(
    dashboard_id: str,
    widget_id: str,
    payload: DashboardWidgetPatch,
    repo: Annotated[DashboardRepository, Depends(get_dashboard_repository)],
) -> DashboardWidgetOut:
    widget = repo.get_widget(dashboard_id, widget_id)
    if widget is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Widget not found")
    try:
        return repo.update_widget(widget, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.delete("/{dashboard_id}/widgets/{widget_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a widget")
def delete_widget(
    dashboard_id: str,
    widget_id: str,
    repo: Annotated[DashboardRepository, Depends(get_dashboard_repository)],
) -> None:
    widget = repo.get_widget(dashboard_id, widget_id)
    if widget is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Widget not found")
    repo.delete_widget(widget)
