import { rangeToStart } from "@/lib/api/telemetry";
import type { AggregatedPoint, MetricName } from "@/lib/types";
import type { DashboardWidgetConfig, WidgetAggregation } from "@/lib/dashboards/types";
import type { QueryAggregation, QueryBucket, QueryMetric, TelemetryQueryRequest, TelemetryQueryResponse, WidgetQueryKeyInput } from "./types";

const MAX_HISTORICAL_WINDOW_MS = 31 * 24 * 60 * 60 * 1000;
const MAX_QUERY_POINTS = 10_000;

export const QUERY_BUCKET_MS: Record<QueryBucket, number | null> = {
  raw: null,
  "10s": 10_000,
  "1m": 60_000,
  "5m": 300_000,
  "15m": 900_000,
  "1h": 3_600_000,
};

const EFFECTIVE_BUCKET_ORDER: QueryBucket[] = ["10s", "1m", "5m", "15m", "1h"];

export const metricToQueryMetric: Record<MetricName, QueryMetric> = {
  latency: "latency",
  throughput: "throughput",
  cpuUsage: "cpu_usage",
  memoryUsage: "memory_usage",
  errorRate: "error_rate",
  payloadSize: "payload_size",
};

export function widgetAggregationToQueryAggregation(aggregation: WidgetAggregation): QueryAggregation {
  return aggregation === "raw" ? "avg" : aggregation;
}

export function widgetBucketToQueryBucket(bucket: DashboardWidgetConfig["bucket"]): QueryBucket {
  return bucket;
}

export function theoreticalBucketCount(start: number, end: number, bucket: QueryBucket): number {
  const bucketMs = QUERY_BUCKET_MS[bucket];
  if (bucketMs === null) return 1;
  return Math.ceil(Math.max(0, end - start) / bucketMs);
}

export function effectiveHistoricalBucket(configuredBucket: QueryBucket, start: number, end: number): QueryBucket {
  if (configuredBucket === "raw") return configuredBucket;
  const configuredIndex = EFFECTIVE_BUCKET_ORDER.indexOf(configuredBucket);
  const candidates = configuredIndex === -1 ? EFFECTIVE_BUCKET_ORDER : EFFECTIVE_BUCKET_ORDER.slice(configuredIndex);
  return candidates.find((bucket) => theoreticalBucketCount(start, end, bucket) <= MAX_QUERY_POINTS) ?? "1h";
}

function isHistoricalRange(widget: DashboardWidgetConfig, sourceKind: string, latestTimestamp: number | null): boolean {
  return sourceKind === "remote" && (widget.timeRange === "1h" || widget.timeRange === "6h" || widget.timeRange === "all") && latestTimestamp !== null;
}

export function isHistoricalLineQuery(widget: DashboardWidgetConfig, sourceKind: string, latestTimestamp: number | null): boolean {
  return isHistoricalRange(widget, sourceKind, latestTimestamp) && widget.type === "line" && widget.bucket !== "raw";
}

export function isHistoricalStatQuery(widget: DashboardWidgetConfig, sourceKind: string, latestTimestamp: number | null): boolean {
  return isHistoricalRange(widget, sourceKind, latestTimestamp) && widget.type === "stat";
}

export function isHistoricalBarQuery(widget: DashboardWidgetConfig, sourceKind: string, latestTimestamp: number | null): boolean {
  return isHistoricalRange(widget, sourceKind, latestTimestamp) && widget.type === "bar" && widget.metric === "throughput" && widget.aggregation === "avg";
}

export function isHistoricalWidgetQuery(widget: DashboardWidgetConfig, sourceKind: string, latestTimestamp: number | null): boolean {
  return isHistoricalLineQuery(widget, sourceKind, latestTimestamp) || isHistoricalStatQuery(widget, sourceKind, latestTimestamp) || isHistoricalBarQuery(widget, sourceKind, latestTimestamp);
}

export function isHistoricalLineWidgetQuery(widget: DashboardWidgetConfig, sourceKind: string, latestTimestamp: number | null): boolean {
  return sourceKind === "remote" && widget.type === "line" && widget.bucket !== "raw" && (widget.timeRange === "1h" || widget.timeRange === "6h" || widget.timeRange === "all") && latestTimestamp !== null;
}

export function normalizeHistoricalEnd(bucket: QueryBucket, latestTimestamp: number): number {
  const bucketMs = QUERY_BUCKET_MS[bucket] ?? 1;
  return Math.floor(latestTimestamp / bucketMs) * bucketMs;
}

export function buildWidgetQueryRequest(widget: DashboardWidgetConfig, latestTimestamp: number, overrides: { bucket?: QueryBucket; groupBy?: TelemetryQueryRequest["groupBy"] } = {}): { request: TelemetryQueryRequest; start: number; end: number; configuredBucket: QueryBucket; effectiveBucket: QueryBucket } {
  const configuredBucket = overrides.bucket ?? widgetBucketToQueryBucket(widget.bucket);
  const provisionalEnd = normalizeHistoricalEnd(configuredBucket, latestTimestamp);
  const provisionalStart = rangeToStart(widget.timeRange, provisionalEnd) ?? provisionalEnd - MAX_HISTORICAL_WINDOW_MS;
  const effectiveBucket = overrides.bucket ?? effectiveHistoricalBucket(configuredBucket, provisionalStart, provisionalEnd);
  const end = normalizeHistoricalEnd(effectiveBucket, latestTimestamp);
  const start = rangeToStart(widget.timeRange, end) ?? end - MAX_HISTORICAL_WINDOW_MS;
  return {
    start,
    end,
    configuredBucket,
    effectiveBucket,
    request: {
      metric: metricToQueryMetric[widget.metric],
      aggregation: widgetAggregationToQueryAggregation(widget.aggregation),
      bucket: effectiveBucket,
      groupBy: overrides.groupBy,
      start: start === undefined ? undefined : new Date(start).toISOString(),
      end: new Date(end).toISOString(),
      filters: {
        ...(widget.service ? { service: widget.service } : {}),
        ...(widget.region ? { region: widget.region } : {}),
      },
    },
  };
}

export function buildWidgetQueryKey(input: WidgetQueryKeyInput): string {
  return JSON.stringify({
    workspaceId: input.workspaceId ?? "none",
    metric: input.metric,
    aggregation: input.aggregation,
    bucket: input.bucket,
    groupBy: input.groupBy ?? "none",
    service: input.service ?? "all",
    region: input.region ?? "all",
    timeRange: input.timeRange,
    start: input.start ?? "open",
    end: input.end ?? "open",
  });
}

export function queryResponseToAggregatedPoints(response: TelemetryQueryResponse): AggregatedPoint[] {
  const series = response.series.find((item) => item.group === null || item.group === undefined) ?? response.series[0];
  if (!series) return [];
  return series.points
    .filter((point) => point.timestamp && point.value !== null)
    .map((point) => ({
      timestamp: Date.parse(point.timestamp as string),
      avg: point.value as number,
      min: point.value as number,
      max: point.value as number,
      count: point.count,
    }))
    .filter((point) => Number.isFinite(point.timestamp) && Number.isFinite(point.avg))
    .sort((a, b) => a.timestamp - b.timestamp);
}

export function extractScalarValue(response: TelemetryQueryResponse): number | null {
  const series = response.series.find((item) => item.group === null || item.group === undefined);
  const point = series?.points[0];
  return point?.value ?? null;
}

export function queryResponseToBars(response: TelemetryQueryResponse): Array<{ service: string; throughput: number; count: number }> {
  return response.series
    .filter((series) => series.group && series.points[0]?.value !== null && series.points[0]?.value !== undefined)
    .map((series) => ({ service: series.group as string, throughput: series.points[0].value as number, count: series.points[0].count }))
    .filter((item) => Number.isFinite(item.throughput))
    .sort((a, b) => a.service.localeCompare(b.service));
}
