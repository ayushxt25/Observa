import type { AggregationMode, MetricName, Region, ServiceId, TimeRange } from "@/lib/types";
import type { ApiMetricQueryResponse, ApiServicesResponse, ApiTelemetryEvent, ApiTelemetryEventsResponse, ApiTelemetryStreamCursorResponse } from "./types";
import { ObservaApiClient } from "./client";
import type { TelemetryEvent } from "@/lib/telemetry/types";

export function mapApiEvent(event: ApiTelemetryEvent): TelemetryEvent {
  return {
    id: event.id,
    timestamp: Date.parse(event.timestamp),
    service: event.service,
    region: event.region,
    latency: event.latency,
    throughput: event.throughput,
    cpuUsage: event.cpuUsage,
    memoryUsage: event.memoryUsage,
    errorRate: event.errorRate,
    payloadSize: event.payloadSize,
    status: event.status,
  };
}

export function mapAggregationToBucket(mode: AggregationMode): "raw" | "1m" | "5m" | "1h" {
  if (mode === "1min") return "1m";
  if (mode === "5min") return "5m";
  if (mode === "1hour") return "1h";
  return "raw";
}

export function rangeToStart(range: TimeRange, latestTimestamp: number): number | undefined {
  if (range === "5m") return latestTimestamp - 300_000;
  if (range === "15m") return latestTimestamp - 900_000;
  if (range === "1h") return latestTimestamp - 3_600_000;
  if (range === "6h") return latestTimestamp - 21_600_000;
  return undefined;
}

function appendQuery(path: string, params: Record<string, string | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "all") search.set(key, value);
  }
  const value = search.toString();
  return value ? `${path}?${value}` : path;
}

export class TelemetryApi {
  constructor(private readonly client: ObservaApiClient) {}

  async fetchEvents(options: {
    signal?: AbortSignal;
    start?: number;
    end?: number;
    service?: ServiceId | "all";
    region?: Region;
    limit?: number;
  } = {}): Promise<TelemetryEvent[]> {
    const path = appendQuery("/api/v1/telemetry", {
      start: options.start === undefined ? undefined : new Date(options.start).toISOString(),
      end: options.end === undefined ? undefined : new Date(options.end).toISOString(),
      service: options.service,
      region: options.region,
      limit: options.limit === undefined ? undefined : String(options.limit),
    });
    const response = await this.client.get<ApiTelemetryEventsResponse>(path, { signal: options.signal });
    if (!Array.isArray(response.events)) throw new Error("Invalid telemetry response");
    return response.events.map(mapApiEvent);
  }

  async fetchServices(signal?: AbortSignal): Promise<ServiceId[]> {
    const response = await this.client.get<ApiServicesResponse>("/api/v1/services", { signal });
    if (!Array.isArray(response.services)) throw new Error("Invalid services response");
    return response.services.map((item) => item.service).filter(Boolean);
  }

  async fetchStreamCursor(signal?: AbortSignal): Promise<string> {
    const response = await this.client.get<ApiTelemetryStreamCursorResponse>("/api/v1/telemetry/stream/cursor", { signal });
    if (typeof response.cursor !== "string") throw new Error("Invalid stream cursor response");
    return response.cursor;
  }

  async queryMetric(options: {
    signal?: AbortSignal;
    metric: MetricName;
    aggregation: "avg" | "min" | "max" | "sum" | "count";
    bucket: AggregationMode | "1m" | "5m" | "1h";
    service?: ServiceId | "all";
    region?: Region;
    start?: number;
    end?: number;
  }): Promise<ApiMetricQueryResponse> {
    const path = appendQuery("/api/v1/metrics/query", {
      metric: options.metric,
      aggregation: options.aggregation,
      bucket: options.bucket === "1m" || options.bucket === "5m" || options.bucket === "1h" ? options.bucket : mapAggregationToBucket(options.bucket),
      service: options.service,
      region: options.region,
      start: options.start === undefined ? undefined : new Date(options.start).toISOString(),
      end: options.end === undefined ? undefined : new Date(options.end).toISOString(),
    });
    return this.client.get<ApiMetricQueryResponse>(path, { signal: options.signal });
  }
}
