import { aggregateLatency, buildHeatmap, queryTelemetry, rangeStartFor } from "@/lib/telemetry/query";
import type { AggregatedPoint, HeatmapCell, MetricName, TelemetryPoint } from "@/lib/types";
import type { DashboardWidgetConfig, ThresholdState } from "./types";
import { evaluateThreshold } from "./thresholds";
import { widgetBucketToAggregationPeriod } from "./types";

export function metricValue(point: TelemetryPoint, metric: MetricName): number {
  if (metric === "latency") return point.latency;
  if (metric === "throughput") return point.throughput;
  if (metric === "cpuUsage") return point.cpuUsage;
  if (metric === "memoryUsage") return point.memoryUsage;
  if (metric === "errorRate") return point.errorRate;
  return point.payloadSize;
}

export function filterWidgetPoints(points: readonly TelemetryPoint[], widget: DashboardWidgetConfig): TelemetryPoint[] {
  return queryTelemetry(points, {
    startTime: rangeStartFor(points, widget.timeRange),
    service: widget.service ?? "all",
    aggregation: widgetBucketToAggregationPeriod(widget.bucket),
  }).filter((point) => !widget.region || point.region === widget.region);
}

export function buildWidgetLine(points: readonly TelemetryPoint[], widget: DashboardWidgetConfig): AggregatedPoint[] {
  if (widget.metric === "latency") return aggregateLatency(points, widgetBucketToAggregationPeriod(widget.bucket));
  const raw = points.map((point) => {
    const value = metricValue(point, widget.metric);
    return { timestamp: point.timestamp, avg: value, min: value, max: value, count: 1 };
  });
  if (widget.bucket === "raw") return raw;
  const bucketMs = widget.bucket === "1m" ? 60_000 : widget.bucket === "5m" ? 300_000 : 3_600_000;
  const buckets = new Map<number, { sum: number; min: number; max: number; count: number }>();
  for (const point of raw) {
    const bucket = Math.floor(point.timestamp / bucketMs) * bucketMs;
    const current = buckets.get(bucket);
    if (current) {
      current.sum += point.avg;
      current.min = Math.min(current.min, point.avg);
      current.max = Math.max(current.max, point.avg);
      current.count += 1;
    } else {
      buckets.set(bucket, { sum: point.avg, min: point.avg, max: point.avg, count: 1 });
    }
  }
  return Array.from(buckets.entries()).sort((a, b) => a[0] - b[0]).map(([timestamp, bucket]) => ({
    timestamp,
    avg: bucket.sum / bucket.count,
    min: bucket.min,
    max: bucket.max,
    count: bucket.count,
  }));
}

export function buildWidgetHeatmap(points: readonly TelemetryPoint[]): HeatmapCell[] {
  return buildHeatmap(points);
}

export function summarizeWidget(points: readonly TelemetryPoint[], widget: DashboardWidgetConfig): { value: number | null; state: ThresholdState } {
  if (points.length === 0) return { value: null, state: "normal" };
  let total = 0;
  for (const point of points) total += metricValue(point, widget.metric);
  const value = total / points.length;
  return { value, state: evaluateThreshold(value, widget) };
}
