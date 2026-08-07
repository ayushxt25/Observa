from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.repositories.telemetry import TelemetryRepository
from app.schemas.telemetry import ServicesResponse
from app.services.metrics import MetricsService

router = APIRouter(prefix="/services", tags=["services"])


def get_services_service(
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> MetricsService:
    return MetricsService(TelemetryRepository(db), settings.max_query_rows)


@router.get("", response_model=ServicesResponse, summary="List observed services")
def list_services(
    service: Annotated[MetricsService, Depends(get_services_service)],
) -> ServicesResponse:
    return service.services()
