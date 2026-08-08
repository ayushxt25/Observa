export const SERVICES = ["auth", "checkout", "search", "payments", "inventory", "notifications"] as const;
export const REGIONS = ["us-east-1", "us-west-2", "eu-central-1", "ap-south-1"] as const;
export const STATUSES = ["healthy", "degraded", "critical"] as const;

export type ServiceId = string;
export type Region = string;
export type TelemetryStatus = (typeof STATUSES)[number];
export type MetricName = "latency" | "throughput" | "cpuUsage" | "memoryUsage" | "errorRate" | "payloadSize";
export type AggregationPeriod = "raw" | "1min" | "5min" | "1hour";
export type TimeRange = "5m" | "15m" | "1h" | "6h" | "all";
export type CapacityPreset = 10000 | 50000 | 100000;

export interface TelemetryEvent {
  id: string;
  timestamp: number;
  service: ServiceId;
  region: Region;
  latency: number;
  throughput: number;
  cpuUsage: number;
  memoryUsage: number;
  errorRate: number;
  payloadSize: number;
  status: TelemetryStatus;
}

export type TelemetryPoint = TelemetryEvent;
export type ServiceName = ServiceId;
export type RegionName = Region;
export type AggregationMode = AggregationPeriod;

export interface TelemetryBatch {
  events: readonly TelemetryEvent[];
}

export interface TelemetrySnapshot {
  version: number;
  retainedCount: number;
  totalReceived: number;
  latestTimestamp: number | null;
  capacity: number;
}

export type TelemetryConnectionState = "idle" | "connecting" | "connected" | "degraded" | "error";
export type TelemetrySourceKind = "simulation" | "remote";

export interface TelemetrySourceStatus {
  kind: TelemetrySourceKind;
  running: boolean;
  paused: boolean;
  intervalMs: number;
  batchSize: number;
  generated: number;
  state?: TelemetryConnectionState;
  message?: string;
}

export interface TelemetryQuery {
  startTime?: number;
  endTime?: number;
  service?: ServiceId | "all";
  aggregation: AggregationPeriod;
}

export interface AggregatedPoint {
  timestamp: number;
  service?: ServiceId;
  avg: number;
  min: number;
  max: number;
  count: number;
}

export interface HeatmapCell {
  service: ServiceId;
  bucketStart: number;
  avgLatency: number;
  errorCount: number;
  count: number;
}

export interface MetricSummary {
  totalPoints: number;
  generatedPoints: number;
  avgLatency: number;
  totalThroughput: number;
  avgErrorRate: number;
}

export type InteractionType = "aggregation" | "filter" | "time-range" | "stress";

export interface InteractionMetric {
  type: InteractionType;
  durationMs: number;
}

export interface VirtualRange {
  startIndex: number;
  endIndex: number;
  offsetTop: number;
  offsetBottom: number;
}
