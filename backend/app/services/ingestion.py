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

    async def ingest(self, events: list[TelemetryEventIn]) -> IngestionResponse:
        started = perf_counter()
        accepted = self.repository.insert_batch(events)
        self.repository.db.commit()
        await self.broker.publish(events)
        duration_ms = (perf_counter() - started) * 1000
        logger.info("telemetry_ingested count=%s duration_ms=%.3f", accepted, duration_ms)
        return IngestionResponse(
            accepted_count=accepted,
            rejected_count=0,
            processing_duration_ms=duration_ms,
        )
