import type { HeatmapCell, ServiceId, TelemetryEvent } from "@/lib/telemetry/types";

export interface TimeSeriesPoint {
  timestamp: number;
  avg: number;
  min: number;
  max: number;
  count: number;
}

export interface BarDatum {
  service: ServiceId;
  throughput: number;
  count: number;
}

export type ScatterDatum = Pick<TelemetryEvent, "id" | "payloadSize" | "latency" | "status">;
export type HeatmapDatum = HeatmapCell;

