from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import Select, and_, case, func, insert, select
from sqlalchemy.orm import Session

from app.models.telemetry import TelemetryEventModel
from app.schemas.metrics import MetricAggregation, MetricBucket, MetricName, MetricPoint, MetricQueryParams
from app.schemas.telemetry import ServiceSummary, TelemetryEventIn


METRIC_COLUMNS = {
    "latency": TelemetryEventModel.latency,
    "throughput": TelemetryEventModel.throughput,
    "cpuUsage": TelemetryEventModel.cpu_usage,
    "memoryUsage": TelemetryEventModel.memory_usage,
    "errorRate": TelemetryEventModel.error_rate,
    "payloadSize": TelemetryEventModel.payload_size,
}

BUCKET_SECONDS: dict[MetricBucket, int | None] = {
    "raw": None,
    "1m": 60,
    "5m": 300,
    "1h": 3600,
}


class TelemetryRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def insert_batch(self, events: list[TelemetryEventIn]) -> int:
        rows = [
            {
                "id": event.id,
                "timestamp": event.timestamp,
                "service": event.service,
                "region": event.region,
                "latency": event.latency,
                "throughput": event.throughput,
                "cpu_usage": event.cpu_usage,
                "memory_usage": event.memory_usage,
                "error_rate": event.error_rate,
                "payload_size": event.payload_size,
                "status": event.status,
            }
            for event in events
        ]
        self.db.execute(insert(TelemetryEventModel), rows)
        return len(rows)

    def metric_points(self, query: MetricQueryParams, max_rows: int) -> tuple[list[MetricPoint], bool]:
        filters = self._filters(query)
        if query.bucket == "raw":
            return self._raw_metric_points(query.metric, filters, max_rows)
        return self._bucketed_metric_points(query, filters, max_rows)

    def service_summaries(self, recent_window_minutes: int = 60) -> list[ServiceSummary]:
        recent_since = datetime.now(timezone.utc) - timedelta(minutes=recent_window_minutes)
        stmt = (
            select(
                TelemetryEventModel.service,
                func.max(TelemetryEventModel.timestamp),
                func.sum(case((TelemetryEventModel.timestamp >= recent_since, 1), else_=0)),
            )
            .group_by(TelemetryEventModel.service)
            .order_by(TelemetryEventModel.service)
        )
        rows = self.db.execute(stmt).all()
        return [
            ServiceSummary(service=row[0], latest_timestamp=row[1], recent_event_count=row[2])
            for row in rows
        ]

    def _filters(self, query: MetricQueryParams) -> list[Any]:
        filters: list[Any] = []
        if query.start is not None:
            filters.append(TelemetryEventModel.timestamp >= query.start)
        if query.end is not None:
            filters.append(TelemetryEventModel.timestamp <= query.end)
        if query.service is not None:
            filters.append(TelemetryEventModel.service == query.service)
        if query.region is not None:
            filters.append(TelemetryEventModel.region == query.region)
        return filters

    def _where(self, stmt: Select[Any], filters: list[Any]) -> Select[Any]:
        if filters:
            return stmt.where(and_(*filters))
        return stmt

    def _raw_metric_points(
        self,
        metric: MetricName,
        filters: list[Any],
        max_rows: int,
    ) -> tuple[list[MetricPoint], bool]:
        metric_column = METRIC_COLUMNS[metric]
        stmt = select(TelemetryEventModel.timestamp, metric_column).order_by(TelemetryEventModel.timestamp)
        stmt = self._where(stmt, filters).limit(max_rows + 1)
        rows = self.db.execute(stmt).all()
        limited = len(rows) > max_rows
        return [
            MetricPoint(timestamp=row[0], value=float(row[1]), count=1)
            for row in rows[:max_rows]
        ], limited

    def _bucketed_metric_points(
        self,
        query: MetricQueryParams,
        filters: list[Any],
        max_rows: int,
    ) -> tuple[list[MetricPoint], bool]:
        metric_column = METRIC_COLUMNS[query.metric]
        aggregate_expr = self._aggregate_expression(metric_column, query.aggregation)
        bucket_seconds = BUCKET_SECONDS[query.bucket]
        if bucket_seconds is None:
            raise ValueError("bucketed query requires a non-raw bucket")

        bucket_expr = func.to_timestamp(
            func.floor(func.extract("epoch", TelemetryEventModel.timestamp) / bucket_seconds)
            * bucket_seconds
        ).label("bucket")
        stmt = (
            select(bucket_expr, aggregate_expr.label("value"), func.count(TelemetryEventModel.id))
            .group_by(bucket_expr)
            .order_by(bucket_expr)
            .limit(max_rows + 1)
        )
        stmt = self._where(stmt, filters)
        rows = self.db.execute(stmt).all()
        limited = len(rows) > max_rows
        return [
            MetricPoint(timestamp=row[0], value=float(row[1]), count=row[2])
            for row in rows[:max_rows]
        ], limited

    def _aggregate_expression(self, metric_column: Any, aggregation: MetricAggregation) -> Any:
        if aggregation == "avg":
            return func.avg(metric_column)
        if aggregation == "min":
            return func.min(metric_column)
        if aggregation == "max":
            return func.max(metric_column)
        if aggregation == "sum":
            return func.sum(metric_column)
        return func.count(metric_column)
