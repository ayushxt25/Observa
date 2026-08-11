import { ObservaApiClient } from "@/lib/api/client";
import { getObservaApiUrl } from "@/lib/api/config";
import { TelemetryApi } from "@/lib/api/telemetry";
import { RemoteTelemetrySource } from "./remoteSource";
import { SimulationTelemetrySource } from "./source";
import type { TelemetrySourceKind, TelemetryEvent } from "./types";
import type { TelemetrySource } from "./source";

export interface SourceFactoryOptions {
  initialData: readonly TelemetryEvent[];
  batchSize: number;
}

export function createTelemetrySource(kind: TelemetrySourceKind, options: SourceFactoryOptions): TelemetrySource {
  if (kind === "remote") {
    const api = new TelemetryApi(new ObservaApiClient({ baseUrl: getObservaApiUrl() }));
    return new RemoteTelemetrySource({ api, pollIntervalMs: 5_000 });
  }
  return new SimulationTelemetrySource({
    seed: 42,
    intervalMs: 100,
    batchSize: options.batchSize,
    startTimestamp: options.initialData.at(-1)?.timestamp ?? 0,
    initialSequence: options.initialData.length,
    generated: options.initialData.length,
  });
}
