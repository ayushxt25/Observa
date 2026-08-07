import logging
from time import perf_counter

from app.repositories.telemetry import TelemetryRepository
from app.schemas.metrics import MetricQueryParams, MetricQueryResponse
from app.schemas.telemetry import ServicesResponse

logger = logging.getLogger(__name__)


class MetricsService:
    def __init__(self, repository: TelemetryRepository, max_query_rows: int) -> None:
        self.repository = repository
        self.max_query_rows = max_query_rows

    def query(self, params: MetricQueryParams) -> MetricQueryResponse:
        params.validate_range()
        started = perf_counter()
        points, limited = self.repository.metric_points(params, self.max_query_rows)
        duration_ms = (perf_counter() - started) * 1000
        logger.info(
            "metric_query metric=%s bucket=%s rows=%s duration_ms=%.3f",
            params.metric,
            params.bucket,
            len(points),
            duration_ms,
        )
        return MetricQueryResponse(
            metric=params.metric,
            aggregation=params.aggregation,
            bucket=params.bucket,
            points=points,
            processing_duration_ms=duration_ms,
            limited=limited,
        )

    def services(self) -> ServicesResponse:
        return ServicesResponse(services=self.repository.service_summaries())
