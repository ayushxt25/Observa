import { SERVICES, type AggregatedPoint, type AggregationMode, type HeatmapCell, type MetricSummary, type ServiceName, type TelemetryPoint, type TimeRange } from "./types";

export function bucketMsFor(mode: AggregationMode): number {
  if (mode === "1min") return 60_000;
  if (mode === "5min") return 300_000;
  if (mode === "1hour") return 3_600_000;
  return 0;
}

export function rangeStartFor(points: readonly TelemetryPoint[], range: TimeRange): number {
  const last = points.at(-1)?.timestamp ?? Date.now();
  if (range === "5m") return last - 300_000;
  if (range === "15m") return last - 900_000;
  if (range === "1h") return last - 3_600_000;
  if (range === "6h") return last - 21_600_000;
  return Number.NEGATIVE_INFINITY;
}

export function filterTelemetry(points: readonly TelemetryPoint[], service: ServiceName | "all", range: TimeRange): TelemetryPoint[] {
  const start = rangeStartFor(points, range);
  return points.filter((point) => point.timestamp >= start && (service === "all" || point.service === service));
}

export function aggregateLatency(points: readonly TelemetryPoint[], mode: AggregationMode): AggregatedPoint[] {
  if (mode === "raw") {
    return points.map((point) => ({ timestamp: point.timestamp, avg: point.latency, min: point.latency, max: point.latency, count: 1 }));
  }

  const bucketMs = bucketMsFor(mode);
  const buckets = new Map<number, { sum: number; min: number; max: number; count: number }>();
  for (const point of points) {
    const bucket = Math.floor(point.timestamp / bucketMs) * bucketMs;
    const current = buckets.get(bucket);
    if (current) {
      current.sum += point.latency;
      current.min = Math.min(current.min, point.latency);
      current.max = Math.max(current.max, point.latency);
      current.count += 1;
    } else {
      buckets.set(bucket, { sum: point.latency, min: point.latency, max: point.latency, count: 1 });
    }
  }

  return Array.from(buckets.entries())
    .sort((a, b) => a[0] - b[0])
    .map(([timestamp, bucket]) => ({
      timestamp,
      avg: bucket.sum / bucket.count,
      min: bucket.min,
      max: bucket.max,
      count: bucket.count,
    }));
}

export function buildHeatmap(points: readonly TelemetryPoint[], bucketCount = 36): HeatmapCell[] {
  if (points.length === 0) return [];
  const first = points[0].timestamp;
  const last = points[points.length - 1].timestamp;
  const width = Math.max(1, Math.ceil((last - first) / bucketCount));
  const buckets = new Map<string, { service: ServiceName; bucketStart: number; latencySum: number; errorCount: number; count: number }>();

  for (const point of points) {
    const bucketStart = first + Math.floor((point.timestamp - first) / width) * width;
    const key = `${point.service}:${bucketStart}`;
    const current = buckets.get(key);
    if (current) {
      current.latencySum += point.latency;
      current.errorCount += point.status === "critical" || point.errorRate > 1 ? 1 : 0;
      current.count += 1;
    } else {
      buckets.set(key, {
        service: point.service,
        bucketStart,
        latencySum: point.latency,
        errorCount: point.status === "critical" || point.errorRate > 1 ? 1 : 0,
        count: 1,
      });
    }
  }

  return Array.from(buckets.values()).map((cell) => ({
    service: cell.service,
    bucketStart: cell.bucketStart,
    avgLatency: cell.latencySum / cell.count,
    errorCount: cell.errorCount,
    count: cell.count,
  }));
}

export function summarize(points: readonly TelemetryPoint[], generatedPoints: number): MetricSummary {
  if (points.length === 0) {
    return { totalPoints: 0, generatedPoints, avgLatency: 0, totalThroughput: 0, avgErrorRate: 0 };
  }
  let latency = 0;
  let throughput = 0;
  let errorRate = 0;
  const recent = points.slice(-1200);
  for (const point of recent) {
    latency += point.latency;
    throughput += point.throughput;
    errorRate += point.errorRate;
  }
  return {
    totalPoints: points.length,
    generatedPoints,
    avgLatency: latency / recent.length,
    totalThroughput: throughput,
    avgErrorRate: errorRate / recent.length,
  };
}

export function throughputByService(points: readonly TelemetryPoint[]): Array<{ service: ServiceName; throughput: number; count: number }> {
  return SERVICES.map((service) => {
    let throughput = 0;
    let count = 0;
    for (const point of points) {
      if (point.service === service) {
        throughput += point.throughput;
        count += 1;
      }
    }
    return { service, throughput: count > 0 ? throughput / count : 0, count };
  });
}
