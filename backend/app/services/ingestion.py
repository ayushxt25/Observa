import logging
from time import perf_counter

from app.repositories.telemetry import TelemetryRepository
from app.schemas.telemetry import IngestionResponse, TelemetryEventIn
from app.streaming.broker import TelemetryBroker

logger = logging.getLogger(__name__)


class IngestionService:
    def __init__(self, repository: TelemetryRepository, broker: TelemetryBroker) -> None:
        self.repository = repository
        self.broker = broker

    async def ingest(self, workspace_id: str, events: list[TelemetryEventIn]) -> IngestionResponse:
        started = perf_counter()
        accepted_events = self.repository.insert_batch(workspace_id, events)
        self.repository.db.commit()
        if accepted_events:
            await self.broker.publish(workspace_id, accepted_events)
        duration_ms = (perf_counter() - started) * 1000
        logger.info("telemetry_ingested workspace_id=%s count=%s duration_ms=%.3f", workspace_id, len(accepted_events), duration_ms)
        return IngestionResponse(
            accepted_count=len(accepted_events),
            rejected_count=0,
            processing_duration_ms=duration_ms,
        )
