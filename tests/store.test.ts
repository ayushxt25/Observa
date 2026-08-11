import { describe, expect, it, vi } from "vitest";
import { TelemetryStore } from "@/lib/telemetry/store";
import type { TelemetryEvent } from "@/lib/telemetry/types";

function event(timestamp: number, id = `${timestamp}`): TelemetryEvent {
  return {
    id,
    timestamp,
    service: "auth",
    region: "us-east-1",
    latency: timestamp,
    throughput: 1,
    cpuUsage: 1,
    memoryUsage: 1,
    errorRate: 0,
    payloadSize: 1,
    status: "healthy",
  };
}

describe("TelemetryStore", () => {
  it("tracks versioning, subscription and capacity", () => {
    const store = new TelemetryStore(2);
    const listener = vi.fn();
    const unsubscribe = store.subscribe(listener);
    store.appendBatch([event(1), event(2), event(3)]);
    expect(store.getSnapshot()).toMatchObject({ version: 1, retainedCount: 2, totalReceived: 3, latestTimestamp: 3, capacity: 2 });
    expect(store.readAll().map((item) => item.timestamp)).toEqual([2, 3]);
    expect(listener).toHaveBeenCalledTimes(1);
    unsubscribe();
    store.append(event(4));
    expect(listener).toHaveBeenCalledTimes(1);
  });

  it("resizes capacity without unbounding retained data", () => {
    const store = new TelemetryStore(3, [event(1), event(2), event(3)]);
    store.setCapacity(2);
    expect(store.getSnapshot().retainedCount).toBe(2);
    expect(store.readAll().map((item) => item.timestamp)).toEqual([2, 3]);
  });

  it("deduplicates telemetry ids during batch append", () => {
    const store = new TelemetryStore(10, [event(1, "a")]);
    store.appendBatch([event(1, "a"), event(2, "b"), event(2, "b")]);
    expect(store.readAll().map((item) => item.id)).toEqual(["a", "b"]);
    expect(store.getSnapshot()).toMatchObject({ retainedCount: 2, totalReceived: 2 });
  });
});
