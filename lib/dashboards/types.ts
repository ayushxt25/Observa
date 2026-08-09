import type { AggregationPeriod, MetricName, Region, ServiceId, TimeRange } from "@/lib/types";

export type WidgetType = "line" | "bar" | "scatter" | "heatmap" | "stat";
export type WidgetAggregation = "raw" | "avg" | "min" | "max" | "sum" | "count";
export type MetricBucket = "raw" | "1m" | "5m" | "1h";
export type ThresholdState = "normal" | "warning" | "critical";

export interface DashboardWidgetConfig {
  id: string;
  dashboardId: string;
  title: string;
  type: WidgetType;
  metric: MetricName;
  service?: ServiceId;
  region?: Region;
  aggregation: WidgetAggregation;
  bucket: MetricBucket;
  timeRange: TimeRange;
  position: number;
  width: 1 | 2;
  height: 1 | 2;
  thresholdWarning?: number;
  thresholdCritical?: number;
}

export interface DashboardConfig {
  id: string;
  name: string;
  description?: string;
  system: boolean;
  widgets: DashboardWidgetConfig[];
}

export interface WidgetDraft {
  title: string;
  type: WidgetType;
  metric: MetricName;
  aggregation: WidgetAggregation;
  bucket: MetricBucket;
  timeRange: TimeRange;
  service?: ServiceId;
  region?: Region;
  thresholdWarning?: number;
  thresholdCritical?: number;
}

export interface MetricQueryKey {
  workspaceId?: string;
  metric: MetricName;
  aggregation: WidgetAggregation;
  bucket: MetricBucket;
  service?: ServiceId;
  region?: Region;
  timeRange: TimeRange;
  sourceVersion: number;
}

export function widgetBucketToAggregationPeriod(bucket: MetricBucket): AggregationPeriod {
  if (bucket === "1m") return "1min";
  if (bucket === "5m") return "5min";
  if (bucket === "1h") return "1hour";
  return "raw";
}
