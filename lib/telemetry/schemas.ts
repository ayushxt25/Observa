import { REGIONS, SERVICES, STATUSES, type TelemetryEvent } from "./types";

export function isTelemetryEvent(value: unknown): value is TelemetryEvent {
  if (typeof value !== "object" || value === null) return false;
  const event = value as Record<string, unknown>;
  return (
    typeof event.id === "string" &&
    typeof event.timestamp === "number" &&
    SERVICES.includes(event.service as never) &&
    REGIONS.includes(event.region as never) &&
    typeof event.latency === "number" &&
    typeof event.throughput === "number" &&
    typeof event.cpuUsage === "number" &&
    typeof event.memoryUsage === "number" &&
    typeof event.errorRate === "number" &&
    typeof event.payloadSize === "number" &&
    STATUSES.includes(event.status as never)
  );
}

export function assertTelemetryBatch(events: readonly unknown[]): readonly TelemetryEvent[] {
  if (!events.every(isTelemetryEvent)) {
    throw new Error("Invalid telemetry batch");
  }
  return events;
}

