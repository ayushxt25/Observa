from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_workspace, require_workspace_role
from app.core import audit_actions
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.models.auth import WorkspaceMembershipModel
from app.repositories.services import ServiceCatalogRepository
from app.repositories.telemetry import TelemetryRepository
from app.schemas.services import (
    ServiceCatalogCreate,
    ServiceCatalogListResponse,
    ServiceCatalogOut,
    ServiceCatalogPatch,
    ServiceDependencyCreate,
    ServiceDependencyListResponse,
    ServiceDependencyOut,
    ServiceDependencyPatch,
    ServiceSummaryResponse,
)
from app.schemas.telemetry import ServicesResponse
from app.services.metrics import MetricsService
from app.services.audit import AuditService, changed_fields

router = APIRouter(prefix="/services", tags=["services"])
dependency_router = APIRouter(prefix="/service-dependencies", tags=["services"])


def get_services_service(
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> MetricsService:
    return MetricsService(TelemetryRepository(db), settings.max_query_rows)


def get_catalog_repository(db: Annotated[Session, Depends(get_db)]) -> ServiceCatalogRepository:
    return ServiceCatalogRepository(db)


def load_service(repo: ServiceCatalogRepository, service_id: str, workspace_id: str):
    service = repo.get(service_id, workspace_id)
    if service is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")
    return service


def load_dependency(repo: ServiceCatalogRepository, dependency_id: str, workspace_id: str):
    dependency = repo.get_dependency(dependency_id, workspace_id)
    if dependency is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service dependency not found")
    return dependency


@router.get("", response_model=ServicesResponse, summary="List observed services")
def list_services(
    service: Annotated[MetricsService, Depends(get_services_service)],
    membership: Annotated[WorkspaceMembershipModel, Depends(get_current_workspace)],
) -> ServicesResponse:
    return service.services(membership.workspace_id)


@router.get("/catalog", response_model=ServiceCatalogListResponse, summary="List service catalog")
def list_catalog(
    repo: Annotated[ServiceCatalogRepository, Depends(get_catalog_repository)],
    membership: Annotated[WorkspaceMembershipModel, Depends(require_workspace_role("viewer"))],
) -> ServiceCatalogListResponse:
    return ServiceCatalogListResponse(services=[repo.to_out(service) for service in repo.list(membership.workspace_id)])


@router.post("/catalog", response_model=ServiceCatalogOut, status_code=status.HTTP_201_CREATED, summary="Create service metadata")
def create_catalog_service(
    payload: ServiceCatalogCreate,
    request: Request,
    repo: Annotated[ServiceCatalogRepository, Depends(get_catalog_repository)],
    membership: Annotated[WorkspaceMembershipModel, Depends(require_workspace_role("member"))],
) -> ServiceCatalogOut:
    try:
        service = repo.create(payload, membership.workspace_id, commit=False)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    AuditService(repo.db).record_user(membership=membership, action=audit_actions.SERVICE_CREATED, resource_type="service", resource_id=service.id, request=request, metadata={"name": service.name, "displayName": service.display_name}, commit=False)
    repo.db.commit()
    repo.db.refresh(service)
    return repo.to_out(service)


@router.get("/catalog/{service_id}", response_model=ServiceCatalogOut, summary="Get service metadata")
def get_catalog_service(
    service_id: str,
    repo: Annotated[ServiceCatalogRepository, Depends(get_catalog_repository)],
    membership: Annotated[WorkspaceMembershipModel, Depends(require_workspace_role("viewer"))],
) -> ServiceCatalogOut:
    return repo.to_out(load_service(repo, service_id, membership.workspace_id))


@router.patch("/catalog/{service_id}", response_model=ServiceCatalogOut, summary="Update service metadata")
def update_catalog_service(
    service_id: str,
    payload: ServiceCatalogPatch,
    request: Request,
    repo: Annotated[ServiceCatalogRepository, Depends(get_catalog_repository)],
    membership: Annotated[WorkspaceMembershipModel, Depends(require_workspace_role("member"))],
) -> ServiceCatalogOut:
    service = load_service(repo, service_id, membership.workspace_id)
    before = {
        "displayName": service.display_name,
        "description": service.description,
        "environment": service.environment,
        "version": service.version,
        "ownerTeam": service.owner_team,
        "repositoryUrl": service.repository_url,
        "runbookUrl": service.runbook_url,
        "tags": repo.to_out(service).tags,
    }
    updated = repo.update(service, payload, commit=False)
    after = {
        "displayName": updated.display_name,
        "description": updated.description,
        "environment": updated.environment,
        "version": updated.version,
        "ownerTeam": updated.owner_team,
        "repositoryUrl": updated.repository_url,
        "runbookUrl": updated.runbook_url,
        "tags": repo.to_out(updated).tags,
    }
    AuditService(repo.db).record_user(membership=membership, action=audit_actions.SERVICE_UPDATED, resource_type="service", resource_id=service_id, request=request, metadata={"name": updated.name, **changed_fields(before, after)}, commit=False)
    repo.db.commit()
    repo.db.refresh(updated)
    return repo.to_out(updated)


@router.delete("/catalog/{service_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete service metadata")
def delete_catalog_service(
    service_id: str,
    request: Request,
    repo: Annotated[ServiceCatalogRepository, Depends(get_catalog_repository)],
    membership: Annotated[WorkspaceMembershipModel, Depends(require_workspace_role("member"))],
) -> None:
    service = load_service(repo, service_id, membership.workspace_id)
    metadata = {"name": service.name, "displayName": service.display_name}
    repo.delete(service, commit=False)
    AuditService(repo.db).record_user(membership=membership, action=audit_actions.SERVICE_DELETED, resource_type="service", resource_id=service_id, request=request, metadata=metadata, commit=False)
    repo.db.commit()


@router.get("/catalog/{service_id}/summary", response_model=ServiceSummaryResponse, summary="Get service health summary")
def get_catalog_summary(
    service_id: str,
    repo: Annotated[ServiceCatalogRepository, Depends(get_catalog_repository)],
    membership: Annotated[WorkspaceMembershipModel, Depends(require_workspace_role("viewer"))],
) -> ServiceSummaryResponse:
    return ServiceSummaryResponse(**repo.to_out(load_service(repo, service_id, membership.workspace_id)).model_dump())


@dependency_router.get("", response_model=ServiceDependencyListResponse, summary="List service dependencies")
def list_dependencies(
    repo: Annotated[ServiceCatalogRepository, Depends(get_catalog_repository)],
    membership: Annotated[WorkspaceMembershipModel, Depends(require_workspace_role("viewer"))],
) -> ServiceDependencyListResponse:
    return ServiceDependencyListResponse(dependencies=[repo.dependency_to_out(item) for item in repo.list_dependencies(membership.workspace_id)])


@dependency_router.post("", response_model=ServiceDependencyOut, status_code=status.HTTP_201_CREATED, summary="Create service dependency")
def create_dependency(
    payload: ServiceDependencyCreate,
    request: Request,
    repo: Annotated[ServiceCatalogRepository, Depends(get_catalog_repository)],
    membership: Annotated[WorkspaceMembershipModel, Depends(require_workspace_role("member"))],
) -> ServiceDependencyOut:
    try:
        dependency = repo.create_dependency(payload, membership.workspace_id, commit=False)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    AuditService(repo.db).record_user(membership=membership, action=audit_actions.SERVICE_DEPENDENCY_CREATED, resource_type="service_dependency", resource_id=dependency.id, request=request, metadata={"sourceServiceId": dependency.source_service_id, "targetServiceId": dependency.target_service_id, "dependencyType": dependency.dependency_type}, commit=False)
    repo.db.commit()
    repo.db.refresh(dependency)
    return repo.dependency_to_out(load_dependency(repo, dependency.id, membership.workspace_id))


@dependency_router.patch("/{dependency_id}", response_model=ServiceDependencyOut, summary="Update service dependency")
def update_dependency(
    dependency_id: str,
    payload: ServiceDependencyPatch,
    request: Request,
    repo: Annotated[ServiceCatalogRepository, Depends(get_catalog_repository)],
    membership: Annotated[WorkspaceMembershipModel, Depends(require_workspace_role("member"))],
) -> ServiceDependencyOut:
    dependency = load_dependency(repo, dependency_id, membership.workspace_id)
    before = {"dependencyType": dependency.dependency_type}
    try:
        updated = repo.update_dependency(dependency, payload, commit=False)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    AuditService(repo.db).record_user(membership=membership, action=audit_actions.SERVICE_DEPENDENCY_UPDATED, resource_type="service_dependency", resource_id=dependency_id, request=request, metadata=changed_fields(before, {"dependencyType": updated.dependency_type}), commit=False)
    repo.db.commit()
    repo.db.refresh(updated)
    return repo.dependency_to_out(load_dependency(repo, updated.id, membership.workspace_id))


@dependency_router.delete("/{dependency_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete service dependency")
def delete_dependency(
    dependency_id: str,
    request: Request,
    repo: Annotated[ServiceCatalogRepository, Depends(get_catalog_repository)],
    membership: Annotated[WorkspaceMembershipModel, Depends(require_workspace_role("member"))],
) -> None:
    dependency = load_dependency(repo, dependency_id, membership.workspace_id)
    metadata = {"sourceServiceId": dependency.source_service_id, "targetServiceId": dependency.target_service_id, "dependencyType": dependency.dependency_type}
    repo.delete_dependency(dependency, commit=False)
    AuditService(repo.db).record_user(membership=membership, action=audit_actions.SERVICE_DEPENDENCY_DELETED, resource_type="service_dependency", resource_id=dependency_id, request=request, metadata=metadata, commit=False)
    repo.db.commit()
