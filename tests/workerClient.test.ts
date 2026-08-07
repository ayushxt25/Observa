import { describe, expect, it, vi } from "vitest";
import { TelemetryWorkerClient } from "@/lib/workers/telemetryWorkerClient";
import type { TelemetryEvent } from "@/lib/telemetry/types";

function event(timestamp: number, latency: number): TelemetryEvent {
  return {
    id: `${timestamp}`,
    timestamp,
    service: "auth",
    region: "us-east-1",
    latency,
    throughput: 1,
    cpuUsage: 1,
    memoryUsage: 1,
    errorRate: 0,
    payloadSize: 1,
    status: "healthy",
  };
}

describe("TelemetryWorkerClient", () => {
  it("uses main-thread fallback when Worker is unavailable", async () => {
    const originalWorker = globalThis.Worker;
    vi.stubGlobal("Worker", undefined);
    const client = new TelemetryWorkerClient();
    const result = await client.aggregate({
      points: [event(0, 10), event(10_000, 30)],
      mode: "1min",
      service: "all",
      timeRange: "all",
      capacity: 10000,
      processingStartedAt: 12,
    });
    expect(result.points).toEqual([{ timestamp: 0, avg: 20, min: 10, max: 30, count: 2 }]);
    expect(result.processingStartedAt).toBe(12);
    vi.unstubAllGlobals();
    if (originalWorker) vi.stubGlobal("Worker", originalWorker);
  });
});
