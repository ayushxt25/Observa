import type { MetricName, Region, ServiceId, TimeRange } from "@/lib/types";
import type { MetricBucket, WidgetAggregation } from "@/lib/dashboards/types";

export type QueryMetric = "latency" | "throughput" | "cpu_usage" | "memory_usage" | "error_rate" | "payload_size";
export type QueryAggregation = "avg" | "min" | "max" | "sum" | "count" | "p50" | "p90" | "p95" | "p99";
export type QueryBucket = "raw" | "10s" | "1m" | "5m" | "15m" | "1h";
export type QueryGroupBy = "service" | "region" | "status";

export interface QueryFilters {
  service?: ServiceId;
  region?: Region;
  status?: "healthy" | "degraded" | "critical";
}

export interface TelemetryQueryRequest {
  metric: QueryMetric;
  aggregation: QueryAggregation;
  start?: string;
  end?: string;
  windowSeconds?: number;
  bucket: QueryBucket;
  groupBy?: QueryGroupBy;
  filters?: QueryFilters;
  limit?: number;
}

export interface QueryPoint {
  timestamp?: string | null;
  value: number | null;
  count: number;
}

export interface QuerySeries {
  group?: string | null;
  points: QueryPoint[];
}

export interface QueryMetadata {
  start: string;
  end: string;
  executionTimeMs: number;
  returnedPoints: number;
  maxPoints: number;
  maxGroups: number;
  limited: boolean;
  truncatedReason?: string | null;
}

export interface TelemetryQueryResponse {
  metric: QueryMetric;
  unit: string;
  aggregation: QueryAggregation;
  bucket: QueryBucket;
  groupBy?: QueryGroupBy | null;
  filters: QueryFilters;
  series: QuerySeries[];
  metadata: QueryMetadata;
}

export interface WidgetQueryKeyInput {
  workspaceId?: string;
  metric: MetricName;
  aggregation: WidgetAggregation;
  bucket: MetricBucket;
  groupBy?: QueryGroupBy;
  service?: ServiceId;
  region?: Region;
  timeRange: TimeRange;
  start?: number;
  end?: number;
}
