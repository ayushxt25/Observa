import { describe, expect, it } from "vitest";
import { aggregateLatency } from "@/lib/aggregation";
import type { TelemetryPoint } from "@/lib/types";

function point(timestamp: number, latency: number): TelemetryPoint {
  return {
    id: `${timestamp}`,
    timestamp,
    service: "auth",
    region: "us-east-1",
    latency,
    throughput: 10,
    cpuUsage: 20,
    memoryUsage: 30,
    errorRate: 0.1,
    payloadSize: 512,
    status: "healthy",
  };
}

describe("aggregateLatency", () => {
  it("calculates average, min, max and count by minute", () => {
    const result = aggregateLatency([point(0, 10), point(10_000, 30), point(70_000, 50)], "1min");
    expect(result).toEqual([
      { timestamp: 0, avg: 20, min: 10, max: 30, count: 2 },
      { timestamp: 60_000, avg: 50, min: 50, max: 50, count: 1 },
    ]);
  });
});
