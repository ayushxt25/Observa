from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.repositories.telemetry import TelemetryRepository
from app.schemas.telemetry import IngestionResponse, TelemetryBatchIn, TelemetryEventIn
from app.services.ingestion import IngestionService
from app.streaming.broker import TelemetryBroker

router = APIRouter(prefix="/telemetry", tags=["telemetry"])


def get_broker(request: Request) -> TelemetryBroker:
    return request.app.state.broker


def get_ingestion_service(
    db: Annotated[Session, Depends(get_db)],
    broker: Annotated[TelemetryBroker, Depends(get_broker)],
) -> IngestionService:
    return IngestionService(TelemetryRepository(db), broker)


@router.post(
    "",
    response_model=IngestionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ingest one telemetry event",
)
async def ingest_event(
    event: TelemetryEventIn,
    service: Annotated[IngestionService, Depends(get_ingestion_service)],
) -> IngestionResponse:
    return await service.ingest([event])


@router.post(
    "/batch",
    response_model=IngestionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ingest a telemetry event batch",
)
async def ingest_batch(
    batch: TelemetryBatchIn,
    settings: Annotated[Settings, Depends(get_settings)],
    service: Annotated[IngestionService, Depends(get_ingestion_service)],
) -> IngestionResponse:
    if len(batch.events) > settings.max_ingest_batch_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Batch exceeds maximum of {settings.max_ingest_batch_size} events",
        )
    return await service.ingest(batch.events)
