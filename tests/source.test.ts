import { afterEach, describe, expect, it, vi } from "vitest";
import { SimulationTelemetrySource } from "@/lib/telemetry/source";

describe("SimulationTelemetrySource", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("emits deterministic batches for a fixed seed", () => {
    vi.useFakeTimers();
    const first = new SimulationTelemetrySource({ seed: 7, startTimestamp: 1_000, batchSize: 2, intervalMs: 100 });
    const second = new SimulationTelemetrySource({ seed: 7, startTimestamp: 1_000, batchSize: 2, intervalMs: 100 });
    const firstBatches: unknown[] = [];
    const secondBatches: unknown[] = [];
    first.subscribe((batch) => firstBatches.push(batch));
    second.subscribe((batch) => secondBatches.push(batch));
    first.start();
    second.start();
    vi.advanceTimersByTime(100);
    expect(firstBatches).toEqual(secondBatches);
    first.stop();
    second.stop();
  });

  it("stops timer emissions after stop", () => {
    vi.useFakeTimers();
    const source = new SimulationTelemetrySource({ seed: 1, startTimestamp: 0, batchSize: 1, intervalMs: 100 });
    const listener = vi.fn();
    source.subscribe(listener);
    source.start();
    vi.advanceTimersByTime(100);
    source.stop();
    vi.advanceTimersByTime(500);
    expect(listener).toHaveBeenCalledTimes(1);
    expect(source.getStatus().running).toBe(false);
  });
});

