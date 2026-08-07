import { aggregateLatency, buildHeatmap, filterTelemetry } from "@/lib/telemetry/query";
import type { AggregatedPoint, AggregationPeriod, CapacityPreset, HeatmapCell, ServiceId, TelemetryEvent, TimeRange } from "@/lib/telemetry/types";
import type { WorkerRequest, WorkerResponse } from "@/lib/types";

export interface TelemetryWorkerJob {
  points: TelemetryEvent[];
  mode: AggregationPeriod;
  service: ServiceId | "all";
  timeRange: TimeRange;
  capacity: CapacityPreset;
  processingStartedAt: number;
}

export interface TelemetryWorkerResult {
  points: AggregatedPoint[];
  heatmap: HeatmapCell[];
  processingStartedAt: number;
}

function runFallback(job: TelemetryWorkerJob): TelemetryWorkerResult {
  const filtered = filterTelemetry(job.points, job.service, job.timeRange);
  return {
    points: aggregateLatency(filtered, job.mode),
    heatmap: buildHeatmap(filtered),
    processingStartedAt: job.processingStartedAt,
  };
}

export class TelemetryWorkerClient {
  private worker: Worker | null = null;
  private requestId = 0;
  private pending = new Map<number, (result: TelemetryWorkerResult) => void>();

  aggregate(job: TelemetryWorkerJob): Promise<TelemetryWorkerResult> {
    if (typeof Worker === "undefined") return Promise.resolve(runFallback(job));
    this.ensureWorker();
    const id = this.requestId + 1;
    this.requestId = id;
    return new Promise((resolve) => {
      this.pending.set(id, resolve);
      const request: WorkerRequest = { id, type: "aggregate", ...job };
      this.worker?.postMessage(request);
    });
  }

  terminate(): void {
    this.worker?.terminate();
    this.worker = null;
    this.pending.clear();
  }

  private ensureWorker(): void {
    if (this.worker) return;
    this.worker = new Worker(new URL("../../workers/data.worker.ts", import.meta.url));
    this.worker.onmessage = (event: MessageEvent<WorkerResponse>) => {
      const resolve = this.pending.get(event.data.id);
      this.pending.delete(event.data.id);
      resolve?.({ points: event.data.points, heatmap: event.data.heatmap, processingStartedAt: event.data.processingStartedAt });
    };
    this.worker.onerror = () => {
      this.pending.clear();
    };
  }
}
