import { afterEach, describe, expect, it, vi } from "vitest";
import { ObservaApiClient } from "@/lib/api/client";
import { TelemetryApi } from "@/lib/api/telemetry";
import { RemoteTelemetrySource } from "@/lib/telemetry/remoteSource";

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

describe("RemoteTelemetrySource", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("emits fetched backend events and exposes connected status", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(response({
      events: [{
        id: "event-1",
        timestamp: "2026-08-07T12:00:00.000Z",
        service: "api-gateway",
        region: "us-east",
        latency: 100,
        throughput: 200,
        cpuUsage: 40,
        memoryUsage: 50,
        errorRate: 0.2,
        payloadSize: 1024,
        status: "healthy",
      }],
      limited: false,
    }));
    const source = new RemoteTelemetrySource({ api: new TelemetryApi(new ObservaApiClient({ baseUrl: "http://backend.test" })), pollIntervalMs: 1000 });
    const listener = vi.fn();
    source.subscribe(listener);
    source.start();
    await vi.waitFor(() => expect(listener).toHaveBeenCalledTimes(1));
    expect(listener.mock.calls[0]?.[0][0].service).toBe("api-gateway");
    expect(source.getStatus().state).toBe("connected");
    source.stop();
  });

  it("does not create duplicate immediate polling loops", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(response({ events: [], limited: false }));
    const source = new RemoteTelemetrySource({ api: new TelemetryApi(new ObservaApiClient({ baseUrl: "http://backend.test" })), pollIntervalMs: 1000 });
    source.start();
    source.start();
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    source.stop();
  });

  it("reports backend failures as error status", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("connection refused"));
    const source = new RemoteTelemetrySource({ api: new TelemetryApi(new ObservaApiClient({ baseUrl: "http://backend.test" })), pollIntervalMs: 1000 });
    source.start();
    await vi.waitFor(() => expect(source.getStatus().state).toBe("error"));
    expect(source.getStatus().message).toContain("connection refused");
    source.stop();
  });

  it("uses the latest timestamp as an incremental polling watermark", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(response({
        events: [{
          id: "event-1",
          timestamp: "2026-08-07T12:00:00.000Z",
          service: "api-gateway",
          region: "us-east",
          latency: 100,
          throughput: 200,
          cpuUsage: 40,
          memoryUsage: 50,
          errorRate: 0.2,
          payloadSize: 1024,
          status: "healthy",
        }],
        limited: false,
      }))
      .mockResolvedValue(response({ events: [], limited: false }));
    const source = new RemoteTelemetrySource({ api: new TelemetryApi(new ObservaApiClient({ baseUrl: "http://backend.test" })), pollIntervalMs: 10 });
    source.start();
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    await vi.waitFor(() => {
      expect(fetchMock.mock.calls.slice(1).some((call) => String(call[0]).includes("start=2026-08-07T12%3A00%3A00.000Z"))).toBe(true);
    });
    source.stop();
  });
});
