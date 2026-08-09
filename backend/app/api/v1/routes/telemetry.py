import asyncio
from datetime import datetime
import json
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import ValidationError
from redis.exceptions import RedisError
from sqlalchemy.orm import Session

from app.api.deps import get_auth_repository, get_current_workspace, get_workspace_api_key
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.repositories.telemetry import TelemetryRepository
from app.models.auth import WorkspaceApiKeyModel, WorkspaceMembershipModel
from app.repositories.auth import AuthRepository
from app.schemas.metrics import MetricQueryParams
from app.schemas.telemetry import (
    IngestionResponse,
    TelemetryBatchIn,
    TelemetryEventIn,
    TelemetryEventOut,
    TelemetryEventsResponse,
)
from app.services.ingestion import IngestionService
from app.streaming.broker import TelemetryBroker, TelemetryStreamCursorError

router = APIRouter(prefix="/telemetry", tags=["telemetry"])
RAW_TELEMETRY_DEFAULT_LIMIT = 10_000
RAW_TELEMETRY_HARD_LIMIT = 10_000
logger = logging.getLogger(__name__)


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
    api_key: Annotated[WorkspaceApiKeyModel, Depends(get_workspace_api_key)],
    service: Annotated[IngestionService, Depends(get_ingestion_service)],
) -> IngestionResponse:
    return await service.ingest(api_key.workspace_id, [event])


@router.post(
    "/batch",
    response_model=IngestionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ingest a telemetry event batch",
)
async def ingest_batch(
    batch: TelemetryBatchIn,
    settings: Annotated[Settings, Depends(get_settings)],
    api_key: Annotated[WorkspaceApiKeyModel, Depends(get_workspace_api_key)],
    service: Annotated[IngestionService, Depends(get_ingestion_service)],
) -> IngestionResponse:
    if len(batch.events) > settings.max_ingest_batch_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Batch exceeds maximum of {settings.max_ingest_batch_size} events",
        )
    return await service.ingest(api_key.workspace_id, batch.events)


@router.get("", response_model=TelemetryEventsResponse, summary="Query raw telemetry events")
def query_events(
    settings: Annotated[Settings, Depends(get_settings)],
    db: Annotated[Session, Depends(get_db)],
    membership: Annotated[WorkspaceMembershipModel, Depends(get_current_workspace)],
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
    rows, limited = TelemetryRepository(db).events(membership.workspace_id, params, effective_limit, latest=start is None)
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


@router.get("/stream/cursor", summary="Get the current telemetry stream cursor")
async def stream_cursor(
    broker: Annotated[TelemetryBroker, Depends(get_broker)],
    membership: Annotated[WorkspaceMembershipModel, Depends(get_current_workspace)],
) -> dict[str, str]:
    try:
        return {"cursor": await broker.latest_id(membership.workspace_id)}
    except RedisError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Redis stream unavailable") from exc


@router.get("/stream", summary="Stream live telemetry events")
async def stream_events(
    request: Request,
    broker: Annotated[TelemetryBroker, Depends(get_broker)],
    membership: Annotated[WorkspaceMembershipModel, Depends(get_current_workspace)],
    repo: Annotated[AuthRepository, Depends(get_auth_repository)],
    cursor: str | None = None,
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> StreamingResponse:
    start_cursor = cursor or last_event_id or "$"
    try:
        broker.validate_cursor(start_cursor)
    except TelemetryStreamCursorError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    async def event_generator():
        workspace_id = membership.workspace_id
        user_id = membership.user_id
        logger.info("telemetry_stream_connect workspace_id=%s cursor=%s", workspace_id, start_cursor)
        yield "retry: 5000\n\n"
        read_count = 0
        try:
            async for stream_id, events in broker.read_batches(workspace_id, start_cursor):
                if await request.is_disconnected():
                    logger.info("telemetry_stream_disconnect workspace_id=%s cursor=%s", workspace_id, stream_id)
                    break
                read_count += 1
                if read_count % 4 == 0 and repo.get_membership(user_id, workspace_id) is None:
                    logger.info("telemetry_stream_membership_revoked workspace_id=%s user_id=%s", workspace_id, user_id)
                    break
                if not events:
                    yield ": keepalive\n\n"
                    continue
                payload = json.dumps({"events": events}, separators=(",", ":"))
                yield f"id: {stream_id}\nevent: telemetry\ndata: {payload}\n\n"
        except RedisError as exc:
            logger.warning("telemetry_stream_redis_failed workspace_id=%s cursor=%s error=%s", workspace_id, start_cursor, exc)
            yield "retry: 5000\nevent: stream-error\ndata: {\"message\":\"Redis stream unavailable\"}\n\n"
            await asyncio.sleep(5)
        except Exception as exc:
            logger.exception("telemetry_stream_failed workspace_id=%s cursor=%s error=%s", workspace_id, start_cursor, exc)
            yield "retry: 5000\nevent: stream-error\ndata: {\"message\":\"Telemetry stream failed\"}\n\n"
            await asyncio.sleep(5)
        finally:
            logger.info("telemetry_stream_closed workspace_id=%s cursor=%s", workspace_id, start_cursor)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
