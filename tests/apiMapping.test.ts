import { describe, expect, it } from "vitest";
import { ObservaApiClient } from "@/lib/api/client";
import { mapAggregationToBucket, mapApiEvent, rangeToStart, TelemetryApi } from "@/lib/api/telemetry";
import { vi } from "vitest";

describe("API telemetry mapping", () => {
  it("maps backend camelCase events into frontend telemetry events", () => {
    const event = mapApiEvent({
      id: "event-1",
      timestamp: "2026-08-07T12:00:00.000Z",
      service: "api-gateway",
      region: "us-east",
      latency: 123,
      throughput: 456,
      cpuUsage: 50,
      memoryUsage: 60,
      errorRate: 0.4,
      payloadSize: 2048,
      status: "healthy",
    });
    expect(event.timestamp).toBe(Date.parse("2026-08-07T12:00:00.000Z"));
    expect(event.service).toBe("api-gateway");
    expect(event.cpuUsage).toBe(50);
  });

  it("maps frontend aggregation and time ranges to backend query values", () => {
    expect(mapAggregationToBucket("1min")).toBe("1m");
    expect(mapAggregationToBucket("5min")).toBe("5m");
    expect(mapAggregationToBucket("1hour")).toBe("1h");
    expect(rangeToStart("15m", 1_000_000)).toBe(100_000);
  });

  it("maps service discovery responses to service names", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({
      services: [{ service: "api-gateway", latestTimestamp: null, recentEventCount: 10 }],
    })));
    const api = new TelemetryApi(new ObservaApiClient({ baseUrl: "http://backend.test" }));
    await expect(api.fetchServices()).resolves.toEqual(["api-gateway"]);
    vi.restoreAllMocks();
  });
});
