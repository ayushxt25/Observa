from typing import Literal
from dataclasses import dataclass


QueryMetric = Literal["latency", "error_rate", "throughput", "cpu_usage", "memory_usage", "payload_size"]
QueryAggregation = Literal["avg", "min", "max", "sum", "count", "p50", "p90", "p95", "p99"]
QueryBucket = Literal["raw", "10s", "1m", "5m", "15m", "1h"]
QueryGroupBy = Literal["service", "region", "status"]


@dataclass(frozen=True)
class TelemetrySummary:
    event_count: int
    avg_latency: float | None
    avg_error_rate: float | None
    avg_throughput: float | None
