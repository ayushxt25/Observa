from time import perf_counter
from math import ceil

from sqlalchemy.orm import Session

from app.query.metrics import metric_definition
from app.query.repository import BUCKET_SECONDS, TelemetryQueryRepository
from app.query.schemas import QueryMetadata, QueryPoint, QuerySeries, QuerySeriesPoint, TelemetryQueryRequest, TelemetryQueryResponse


class TelemetryQueryEngine:
    def __init__(
        self,
        db: Session,
        *,
        max_range_seconds: int = 2_678_400,
        max_points: int = 10_000,
        max_groups: int = 100,
    ) -> None:
        self.repository = TelemetryQueryRepository(db)
        self.max_range_seconds = max_range_seconds
        self.max_points = max_points
        self.max_groups = max_groups

    def execute(self, workspace_id: str, request: TelemetryQueryRequest) -> TelemetryQueryResponse:
        start, end = request.resolved_range()
        range_seconds = (end - start).total_seconds()
        if range_seconds <= 0:
            raise ValueError("end must be after start")
        if range_seconds > self.max_range_seconds:
            raise ValueError("query range exceeds maximum allowed range")
        requested_limit = request.limit or self.max_points
        max_points = min(requested_limit, self.max_points)
        bucket_seconds = BUCKET_SECONDS[request.bucket]
        if bucket_seconds is not None:
            bucket_count = ceil(range_seconds / bucket_seconds)
            theoretical_points = bucket_count * (self.max_groups if request.group_by is not None else 1)
            if theoretical_points > self.max_points:
                raise ValueError("query bucket resolution exceeds maximum returned points")
        started = perf_counter()
        points, limited, reason = self.repository.execute(
            workspace_id=workspace_id,
            request=request,
            start=start,
            end=end,
            max_points=max_points,
            max_groups=self.max_groups,
        )
        if reason == "max_points" and request.limit is not None and request.limit <= self.max_points:
            reason = "request_limit"
        metric = metric_definition(request.metric)
        series = self._to_series(points)
        return TelemetryQueryResponse(
            metric=request.metric,
            unit=metric.unit,
            aggregation=request.aggregation,
            bucket=request.bucket,
            group_by=request.group_by,
            filters=request.filters,
            series=series,
            metadata=QueryMetadata(
                start=start,
                end=end,
                execution_time_ms=(perf_counter() - started) * 1000,
                returned_points=sum(len(item.points) for item in series),
                max_points=max_points,
                max_groups=self.max_groups,
                limited=limited,
                truncated_reason=reason,
            ),
        )

    def _to_series(self, points: list[QuerySeriesPoint]) -> list[QuerySeries]:
        grouped: dict[str | None, list[QueryPoint]] = {}
        for point in points:
            grouped.setdefault(point.group, []).append(QueryPoint(timestamp=point.timestamp, value=point.value, count=point.count))
        return [
            QuerySeries(group=group, points=sorted(items, key=lambda item: item.timestamp or datetime_min()))
            for group, items in sorted(grouped.items(), key=lambda item: item[0] or "")
        ]


def datetime_min():
    from datetime import datetime, timezone

    return datetime.min.replace(tzinfo=timezone.utc)
