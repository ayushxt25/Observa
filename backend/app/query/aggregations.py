from typing import Any

from sqlalchemy import func

from app.query.models import QueryAggregation


PERCENTILES: dict[QueryAggregation, float] = {
    "p50": 0.50,
    "p90": 0.90,
    "p95": 0.95,
    "p99": 0.99,
}


def aggregation_expression(column: Any, aggregation: QueryAggregation, *, dialect_name: str) -> Any:
    if aggregation == "avg":
        return func.avg(column)
    if aggregation == "min":
        return func.min(column)
    if aggregation == "max":
        return func.max(column)
    if aggregation == "sum":
        return func.sum(column)
    if aggregation == "count":
        return func.count(column)
    percentile = PERCENTILES[aggregation]
    if dialect_name == "postgresql":
        return func.percentile_cont(percentile).within_group(column)
    return None

