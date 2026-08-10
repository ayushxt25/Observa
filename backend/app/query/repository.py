from datetime import datetime
from typing import Any

from sqlalchemy import Select, and_, func, select
from sqlalchemy.orm import Session

from app.models.telemetry import TelemetryEventModel
from app.query.aggregations import PERCENTILES, aggregation_expression
from app.query.metrics import metric_definition
from app.query.models import QueryAggregation, QueryGroupBy
from app.query.schemas import QuerySeriesPoint, TelemetryQueryRequest


BUCKET_SECONDS = {
    "raw": None,
    "10s": 10,
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "1h": 3600,
}

GROUP_COLUMNS = {
    "service": TelemetryEventModel.service,
    "region": TelemetryEventModel.region,
    "status": TelemetryEventModel.status,
}


class TelemetryQueryRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def execute(
        self,
        *,
        workspace_id: str,
        request: TelemetryQueryRequest,
        start: datetime,
        end: datetime,
        max_points: int,
        max_groups: int,
    ) -> tuple[list[QuerySeriesPoint], bool, str | None]:
        if self.db.get_bind().dialect.name != "postgresql":
            return self._execute_sqlite_fallback(
                workspace_id=workspace_id,
                request=request,
                start=start,
                end=end,
                max_points=max_points,
                max_groups=max_groups,
            )
        allowed_groups: set[str] | None = None
        group_limited = False
        if request.group_by is not None:
            allowed_group_list, group_limited = self._limited_groups(
                workspace_id=workspace_id,
                request=request,
                start=start,
                end=end,
                max_groups=max_groups,
            )
            allowed_groups = set(allowed_group_list)
        stmt = self._build_select(workspace_id=workspace_id, request=request, start=start, end=end, allowed_groups=allowed_groups).limit(max_points + 1)
        rows = self.db.execute(stmt).all()
        point_limited = len(rows) > max_points
        selected = rows[:max_points]
        reason = "max_points" if point_limited else ("max_groups" if group_limited else None)
        return [self._row_to_point(row, request.group_by, request.bucket != "raw") for row in selected], point_limited or group_limited, reason

    def _build_select(
        self,
        *,
        workspace_id: str,
        request: TelemetryQueryRequest,
        start: datetime,
        end: datetime,
        allowed_groups: set[str] | None = None,
    ) -> Select[Any]:
        metric = metric_definition(request.metric)
        aggregate = aggregation_expression(metric.column, request.aggregation, dialect_name=self.db.get_bind().dialect.name)
        if aggregate is None:
            raise ValueError("percentile aggregation requires PostgreSQL")
        columns: list[Any] = []
        group_columns: list[Any] = []
        order_columns: list[Any] = []
        bucket_seconds = BUCKET_SECONDS[request.bucket]
        bucket = None
        if bucket_seconds is not None:
            bucket = func.to_timestamp(
                func.floor(func.extract("epoch", TelemetryEventModel.timestamp) / bucket_seconds) * bucket_seconds
            ).label("bucket")
            columns.append(bucket)
            group_columns.append(bucket)
        if request.group_by is not None:
            group_column = GROUP_COLUMNS[request.group_by].label("group_value")
            columns.append(group_column)
            group_columns.append(group_column)
            order_columns.append(group_column)
        if bucket is not None:
            order_columns.append(bucket)
        columns.extend([aggregate.label("value"), func.count(TelemetryEventModel.db_id).label("count")])
        filters = self._filters(workspace_id, request, start, end)
        if allowed_groups is not None and request.group_by is not None:
            filters.append(GROUP_COLUMNS[request.group_by].in_(sorted(allowed_groups)))
        stmt = select(*columns).where(and_(*filters))
        if group_columns:
            stmt = stmt.group_by(*group_columns)
        if order_columns:
            stmt = stmt.order_by(*order_columns)
        return stmt

    def _limited_groups(
        self,
        *,
        workspace_id: str,
        request: TelemetryQueryRequest,
        start: datetime,
        end: datetime,
        max_groups: int,
    ) -> tuple[list[str], bool]:
        if request.group_by is None:
            return [], False
        group_column = GROUP_COLUMNS[request.group_by]
        stmt = (
            select(group_column)
            .where(and_(*self._filters(workspace_id, request, start, end)))
            .group_by(group_column)
            .order_by(group_column)
            .limit(max_groups + 1)
        )
        rows = [str(row[0]) for row in self.db.execute(stmt).all()]
        return rows[:max_groups], len(rows) > max_groups

    def _filters(self, workspace_id: str, request: TelemetryQueryRequest, start: datetime, end: datetime) -> list[Any]:
        filters: list[Any] = [
            TelemetryEventModel.workspace_id == workspace_id,
            TelemetryEventModel.timestamp >= start,
            TelemetryEventModel.timestamp < end,
        ]
        if request.filters.service is not None:
            filters.append(TelemetryEventModel.service == request.filters.service)
        if request.filters.region is not None:
            filters.append(TelemetryEventModel.region == request.filters.region)
        if request.filters.status is not None:
            filters.append(TelemetryEventModel.status == request.filters.status)
        return filters

    def _row_to_point(self, row: Any, group_by: QueryGroupBy | None, has_bucket: bool) -> QuerySeriesPoint:
        index = 0
        timestamp = None
        group = None
        if has_bucket:
            timestamp = row[index]
            index += 1
        if group_by is not None:
            group = str(row[index])
            index += 1
        raw_value = row[index]
        value = float(raw_value) if raw_value is not None else None
        return QuerySeriesPoint(timestamp=timestamp, group=group, value=value, count=int(row[index + 1] or 0))

    def _execute_sqlite_fallback(
        self,
        *,
        workspace_id: str,
        request: TelemetryQueryRequest,
        start: datetime,
        end: datetime,
        max_points: int,
        max_groups: int,
    ) -> tuple[list[QuerySeriesPoint], bool, str | None]:
        metric = metric_definition(request.metric)
        bucket_seconds = BUCKET_SECONDS[request.bucket]
        columns: list[Any] = [TelemetryEventModel.timestamp, metric.column]
        if request.group_by is not None:
            columns.append(GROUP_COLUMNS[request.group_by])
        stmt = select(*columns).where(and_(*self._filters(workspace_id, request, start, end))).order_by(TelemetryEventModel.timestamp)
        rows = self.db.execute(stmt).all()
        grouped: dict[tuple[datetime | None, str | None], list[float]] = {}
        for row in rows:
            timestamp = row[0]
            bucket = None
            if bucket_seconds is not None:
                epoch = int(timestamp.timestamp())
                bucket = datetime.fromtimestamp(epoch - (epoch % bucket_seconds), tz=timestamp.tzinfo)
            group = str(row[2]) if request.group_by is not None else None
            grouped.setdefault((bucket, group), []).append(float(row[1]))
        if not grouped and bucket_seconds is None and request.group_by is None:
            grouped[(None, None)] = []
        points: list[QuerySeriesPoint] = []
        sorted_items = sorted(grouped.items(), key=lambda item: (item[0][1] or "", item[0][0] or datetime.min))
        group_limited = False
        if request.group_by is not None:
            groups = sorted({group for (_bucket, group), _values in sorted_items if group is not None})
            allowed = set(groups[:max_groups])
            group_limited = len(groups) > max_groups
            sorted_items = [item for item in sorted_items if item[0][1] in allowed]
        for (bucket, group), values in sorted_items:
            values.sort()
            value = self._fallback_aggregate(values, request.aggregation)
            points.append(QuerySeriesPoint(timestamp=bucket, group=group, value=value, count=len(values)))
        limited = len(points) > max_points
        reason = "max_points" if limited else ("max_groups" if group_limited else None)
        return points[:max_points], limited or group_limited, reason

    def _fallback_aggregate(self, values: list[float], aggregation: QueryAggregation) -> float | None:
        if not values:
            return 0 if aggregation == "count" else None
        if aggregation == "avg":
            return sum(values) / len(values)
        if aggregation == "min":
            return min(values)
        if aggregation == "max":
            return max(values)
        if aggregation == "sum":
            return sum(values)
        if aggregation == "count":
            return float(len(values))
        percentile = PERCENTILES[aggregation]
        rank = percentile * (len(values) - 1)
        lower = int(rank)
        upper = min(lower + 1, len(values) - 1)
        fraction = rank - lower
        return values[lower] + (values[upper] - values[lower]) * fraction
