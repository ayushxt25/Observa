import { afterEach, describe, expect, it, vi } from "vitest";
import { ObservaApiClient } from "@/lib/api/client";
import { TelemetryStreamClient, type TelemetryStreamHandlers } from "@/lib/api/stream";
import { TelemetryApi } from "@/lib/api/telemetry";
import { RemoteTelemetrySource } from "@/lib/telemetry/remoteSource";
import type { TelemetryEvent } from "@/lib/types";

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

function apiEvent(id: string, timestamp = "2026-08-07T12:00:00.000Z") {
  return {
    id,
    timestamp,
    service: "api-gateway",
    region: "us-east",
    latency: 100,
    throughput: 200,
    cpuUsage: 40,
    memoryUsage: 50,
    errorRate: 0.2,
    payloadSize: 1024,
    status: "healthy",
  };
}

class FakeStreamClient extends TelemetryStreamClient {
  starts = 0;
  stops = 0;
  cursor: string | null = null;
  handlers: TelemetryStreamHandlers | null = null;

  override start(cursor: string, handlers: TelemetryStreamHandlers): void {
    this.starts += 1;
    this.cursor = cursor;
    this.handlers = handlers;
    handlers.onOpen();
  }

  override stop(): void {
    this.stops += 1;
  }

  emit(batch: readonly TelemetryEvent[], streamId: string): void {
    this.handlers?.onBatch(batch, streamId);
  }

  fail(message: string): void {
    this.handlers?.onError(message);
  }
}

function sourceWith(streamClient: FakeStreamClient): RemoteTelemetrySource {
  return new RemoteTelemetrySource({
    api: new TelemetryApi(new ObservaApiClient({ baseUrl: "http://backend.test" })),
    streamClient,
    pollIntervalMs: 50,
  });
}

describe("RemoteTelemetrySource", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("hydrates with HTTP, then opens the stream from the captured cursor", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.includes("/stream/cursor")) return Promise.resolve(response({ cursor: "42-0" }));
      return Promise.resolve(response({ events: [apiEvent("event-1")], limited: false }));
    });
    const stream = new FakeStreamClient();
    const source = sourceWith(stream);
    const listener = vi.fn();
    source.subscribe(listener);
    source.start();
    await vi.waitFor(() => expect(listener).toHaveBeenCalledTimes(1));
    expect(listener.mock.calls[0]?.[0][0].service).toBe("api-gateway");
    expect(stream.cursor).toBe("42-0");
    expect(source.getStatus().state).toBe("connected");
    source.stop();
  });

  it("does not create duplicate streams when start is called twice", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.includes("/stream/cursor")) return Promise.resolve(response({ cursor: "42-0" }));
      return Promise.resolve(response({ events: [], limited: false }));
    });
    const stream = new FakeStreamClient();
    const source = sourceWith(stream);
    source.start();
    source.start();
    await vi.waitFor(() => expect(stream.starts).toBe(1));
    source.stop();
  });

  it("reports backend failures as degraded and starts fallback polling", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("connection refused"));
    const source = sourceWith(new FakeStreamClient());
    source.start();
    await vi.waitFor(() => expect(source.getStatus().state).toBe("degraded"));
    expect(source.getStatus().message).toContain("connection refused");
    source.stop();
  });

  it("uses the latest timestamp as the fallback polling watermark", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.includes("/stream/cursor")) return Promise.resolve(response({ cursor: "42-0" }));
      return Promise.resolve(response({ events: [apiEvent("event-1")], limited: false }));
    });
    const stream = new FakeStreamClient();
    const source = sourceWith(stream);
    source.start();
    await vi.waitFor(() => expect(stream.starts).toBe(1));
    stream.fail("stream down");
    await vi.waitFor(() => {
      expect(fetchMock.mock.calls.some((call) => String(call[0]).includes("start=2026-08-07T12%3A00%3A00.000Z"))).toBe(true);
    });
    source.stop();
  });

  it("closes stream on source stop", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.includes("/stream/cursor")) return Promise.resolve(response({ cursor: "42-0" }));
      return Promise.resolve(response({ events: [], limited: false }));
    });
    const stream = new FakeStreamClient();
    const source = sourceWith(stream);
    source.start();
    await vi.waitFor(() => expect(stream.starts).toBe(1));
    source.stop();
    expect(stream.stops).toBeGreaterThan(0);
  });
});
