from dataclasses import dataclass
from typing import Any

from app.models.telemetry import TelemetryEventModel
from app.query.models import QueryMetric


@dataclass(frozen=True)
class MetricDefinition:
    name: QueryMetric
    column: Any
    unit: str


METRICS: dict[QueryMetric, MetricDefinition] = {
    "latency": MetricDefinition("latency", TelemetryEventModel.latency, "ms"),
    "error_rate": MetricDefinition("error_rate", TelemetryEventModel.error_rate, "percent"),
    "throughput": MetricDefinition("throughput", TelemetryEventModel.throughput, "requests_per_second"),
    "cpu_usage": MetricDefinition("cpu_usage", TelemetryEventModel.cpu_usage, "percent"),
    "memory_usage": MetricDefinition("memory_usage", TelemetryEventModel.memory_usage, "percent"),
    "payload_size": MetricDefinition("payload_size", TelemetryEventModel.payload_size, "bytes"),
}


def metric_definition(metric: QueryMetric) -> MetricDefinition:
    return METRICS[metric]

