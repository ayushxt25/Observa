export type {
  AggregatedPoint,
  AggregationMode,
  AggregationPeriod,
  CapacityPreset,
  HeatmapCell,
  InteractionMetric,
  InteractionType,
  MetricName,
  MetricSummary,
  Region,
  RegionName,
  ServiceId,
  ServiceName,
  TelemetryBatch,
  TelemetryEvent,
  TelemetryPoint,
  TelemetryQuery,
  TelemetrySnapshot,
  TelemetrySourceKind,
  TelemetrySourceStatus,
  TelemetryStatus,
  TimeRange,
  VirtualRange,
} from "./telemetry/types";

export { REGIONS, SERVICES, STATUSES } from "./telemetry/types";

export interface WorkerRequest {
  id: number;
  type: "aggregate" | "stress";
  points: import("./telemetry/types").TelemetryEvent[];
  mode: import("./telemetry/types").AggregationPeriod;
  service: import("./telemetry/types").ServiceId | "all";
  timeRange: import("./telemetry/types").TimeRange;
  capacity: import("./telemetry/types").CapacityPreset;
  processingStartedAt: number;
}

export interface WorkerResponse {
  id: number;
  type: "aggregate" | "stress";
  points: import("./telemetry/types").AggregatedPoint[];
  heatmap: import("./telemetry/types").HeatmapCell[];
  processingStartedAt: number;
}
