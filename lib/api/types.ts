export interface ApiTelemetryEvent {
  id: string;
  timestamp: string;
  service: string;
  region: string;
  latency: number;
  throughput: number;
  cpuUsage: number;
  memoryUsage: number;
  errorRate: number;
  payloadSize: number;
  status: "healthy" | "degraded" | "critical";
  createdAt?: string;
}

export interface ApiTelemetryEventsResponse {
  events: ApiTelemetryEvent[];
  limited: boolean;
}

export interface ApiServiceSummary {
  service: string;
  latestTimestamp: string | null;
  recentEventCount: number;
}

export interface ApiServicesResponse {
  services: ApiServiceSummary[];
}

export interface ApiMetricPoint {
  timestamp: string;
  value: number;
  count: number;
}

export interface ApiMetricQueryResponse {
  metric: string;
  aggregation: string;
  bucket: string;
  points: ApiMetricPoint[];
  processingDurationMs: number;
  limited: boolean;
}
