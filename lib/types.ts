export const SERVICES = ["auth", "checkout", "search", "payments", "inventory", "notifications"] as const;
export const REGIONS = ["us-east-1", "us-west-2", "eu-central-1", "ap-south-1"] as const;
export const STATUSES = ["healthy", "degraded", "critical"] as const;

export type ServiceName = (typeof SERVICES)[number];
export type RegionName = (typeof REGIONS)[number];
export type TelemetryStatus = (typeof STATUSES)[number];

export type AggregationMode = "raw" | "1min" | "5min" | "1hour";
export type CapacityPreset = 10000 | 50000 | 100000;
export type TimeRange = "5m" | "15m" | "1h" | "6h" | "all";

export interface TelemetryPoint {
  id: string;
  timestamp: number;
  service: ServiceName;
  region: RegionName;
  latency: number;
  throughput: number;
  cpuUsage: number;
  memoryUsage: number;
  errorRate: number;
  payloadSize: number;
  status: TelemetryStatus;
}

export interface AggregatedPoint {
  timestamp: number;
  service?: ServiceName;
  avg: number;
  min: number;
  max: number;
  count: number;
}

export interface MetricSummary {
  totalPoints: number;
  generatedPoints: number;
  avgLatency: number;
  totalThroughput: number;
  avgErrorRate: number;
}

export interface WorkerRequest {
  id: number;
  type: "aggregate" | "stress";
  points: TelemetryPoint[];
  mode: AggregationMode;
  service: ServiceName | "all";
  timeRange: TimeRange;
  capacity: CapacityPreset;
}

export interface WorkerResponse {
  id: number;
  type: "aggregate" | "stress";
  points: AggregatedPoint[];
  heatmap: HeatmapCell[];
}

export interface HeatmapCell {
  service: ServiceName;
  bucketStart: number;
  avgLatency: number;
  errorCount: number;
  count: number;
}

export interface VirtualRange {
  startIndex: number;
  endIndex: number;
  offsetTop: number;
  offsetBottom: number;
}
