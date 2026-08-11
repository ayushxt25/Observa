import type { AggregatedPoint, AggregationPeriod, HeatmapCell, MetricSummary, ServiceId, TelemetryEvent, TelemetryQuery, TimeRange } from "./types";

export function bucketMsFor(period: AggregationPeriod): number {
  if (period === "1min") return 60_000;
  if (period === "5min") return 300_000;
  if (period === "1hour") return 3_600_000;
  return 0;
}

export function rangeStartFor(events: readonly TelemetryEvent[], range: TimeRange): number {
  const last = events.at(-1)?.timestamp ?? Date.now();
  if (range === "5m") return last - 300_000;
  if (range === "15m") return last - 900_000;
  if (range === "1h") return last - 3_600_000;
  if (range === "6h") return last - 21_600_000;
  return Number.NEGATIVE_INFINITY;
}

export function queryTelemetry(events: readonly TelemetryEvent[], query: TelemetryQuery): TelemetryEvent[] {
  const service = query.service ?? "all";
  return events.filter((event) => {
    if (query.startTime !== undefined && event.timestamp < query.startTime) return false;
    if (query.endTime !== undefined && event.timestamp > query.endTime) return false;
    return service === "all" || event.service === service;
  });
}

export function filterTelemetry(events: readonly TelemetryEvent[], service: ServiceId | "all", range: TimeRange): TelemetryEvent[] {
  return queryTelemetry(events, { startTime: rangeStartFor(events, range), service, aggregation: "raw" });
}

export function aggregateLatency(events: readonly TelemetryEvent[], period: AggregationPeriod): AggregatedPoint[] {
  if (period === "raw") {
    return events.map((event) => ({ timestamp: event.timestamp, avg: event.latency, min: event.latency, max: event.latency, count: 1 }));
  }
  const bucketMs = bucketMsFor(period);
  const buckets = new Map<number, { sum: number; min: number; max: number; count: number }>();
  for (const event of events) {
    const bucket = Math.floor(event.timestamp / bucketMs) * bucketMs;
    const current = buckets.get(bucket);
    if (current) {
      current.sum += event.latency;
      current.min = Math.min(current.min, event.latency);
      current.max = Math.max(current.max, event.latency);
      current.count += 1;
    } else {
      buckets.set(bucket, { sum: event.latency, min: event.latency, max: event.latency, count: 1 });
    }
  }
  return Array.from(buckets.entries())
    .sort((a, b) => a[0] - b[0])
    .map(([timestamp, bucket]) => ({ timestamp, avg: bucket.sum / bucket.count, min: bucket.min, max: bucket.max, count: bucket.count }));
}

export function buildHeatmap(events: readonly TelemetryEvent[], bucketCount = 36): HeatmapCell[] {
  if (events.length === 0) return [];
  const first = events[0].timestamp;
  const last = events[events.length - 1].timestamp;
  const width = Math.max(1, Math.ceil((last - first) / bucketCount));
  const buckets = new Map<string, { service: ServiceId; bucketStart: number; latencySum: number; errorCount: number; count: number }>();
  for (const event of events) {
    const bucketStart = first + Math.floor((event.timestamp - first) / width) * width;
    const key = `${event.service}:${bucketStart}`;
    const current = buckets.get(key);
    if (current) {
      current.latencySum += event.latency;
      current.errorCount += event.status === "critical" || event.errorRate > 1 ? 1 : 0;
      current.count += 1;
    } else {
      buckets.set(key, { service: event.service, bucketStart, latencySum: event.latency, errorCount: event.status === "critical" || event.errorRate > 1 ? 1 : 0, count: 1 });
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

export function summarize(events: readonly TelemetryEvent[], generatedPoints: number): MetricSummary {
  if (events.length === 0) return { totalPoints: 0, generatedPoints, avgLatency: 0, totalThroughput: 0, avgErrorRate: 0 };
  const recent = events.slice(-1200);
  let latency = 0;
  let throughput = 0;
  let errorRate = 0;
  for (const event of recent) {
    latency += event.latency;
    throughput += event.throughput;
    errorRate += event.errorRate;
  }
  return {
    totalPoints: events.length,
    generatedPoints,
    avgLatency: latency / recent.length,
    totalThroughput: throughput,
    avgErrorRate: errorRate / recent.length,
  };
}

export function throughputByService(events: readonly TelemetryEvent[]): Array<{ service: ServiceId; throughput: number; count: number }> {
  const services = Array.from(new Set(events.map((event) => event.service))).sort();
  return services.map((service) => {
    let throughput = 0;
    let count = 0;
    for (const event of events) {
      if (event.service === service) {
        throughput += event.throughput;
        count += 1;
      }
    }
    return { service, throughput: count > 0 ? throughput / count : 0, count };
  });
}
