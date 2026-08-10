from typing import Literal


QueryMetric = Literal["latency", "error_rate", "throughput", "cpu_usage", "memory_usage", "payload_size"]
QueryAggregation = Literal["avg", "min", "max", "sum", "count", "p50", "p90", "p95", "p99"]
QueryBucket = Literal["raw", "10s", "1m", "5m", "15m", "1h"]
QueryGroupBy = Literal["service", "region", "status"]

