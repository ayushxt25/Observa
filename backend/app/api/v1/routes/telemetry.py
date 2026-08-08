from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.repositories.telemetry import TelemetryRepository
from app.schemas.metrics import MetricQueryParams
from app.schemas.telemetry import (
    IngestionResponse,
    TelemetryBatchIn,
    TelemetryEventIn,
    TelemetryEventOut,
    TelemetryEventsResponse,
)
from app.services.ingestion import IngestionService
from app.streaming.broker import TelemetryBroker

router = APIRouter(prefix="/telemetry", tags=["telemetry"])
RAW_TELEMETRY_DEFAULT_LIMIT = 10_000
RAW_TELEMETRY_HARD_LIMIT = 10_000


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


@router.get("", response_model=TelemetryEventsResponse, summary="Query raw telemetry events")
def query_events(
    settings: Annotated[Settings, Depends(get_settings)],
    db: Annotated[Session, Depends(get_db)],
    start: datetime | None = None,
    end: datetime | None = None,
    service: str | None = None,
    region: str | None = None,
    limit: Annotated[int | None, Query(ge=1)] = None,
) -> TelemetryEventsResponse:
    effective_max = min(settings.max_query_rows, RAW_TELEMETRY_HARD_LIMIT)
    effective_limit = limit if limit is not None else effective_max
    if effective_limit > effective_max:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"limit must be between 1 and {effective_max}",
        )
    try:
        params = MetricQueryParams(start=start, end=end, service=service, region=region)
        params.validate_range()
    except (ValueError, ValidationError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    rows, limited = TelemetryRepository(db).events(params, effective_limit, latest=start is None)
    events = [
        TelemetryEventOut(
            id=row.id,
            timestamp=row.timestamp,
            service=row.service,
            region=row.region,
            latency=row.latency,
            throughput=row.throughput,
            cpu_usage=row.cpu_usage,
            memory_usage=row.memory_usage,
            error_rate=row.error_rate,
            payload_size=row.payload_size,
            status=row.status,
            created_at=row.created_at,
        )
        for row in rows
    ]
    return TelemetryEventsResponse(events=events, limited=limited)
