"use client";

import { useContext, useSyncExternalStore } from "react";
import { TelemetryServicesContext } from "@/components/providers/DataProvider";
import type { TelemetryStore } from "@/lib/telemetry/store";
import type { TelemetrySnapshot } from "@/lib/telemetry/types";

const emptySnapshot: TelemetrySnapshot = {
  version: 0,
  retainedCount: 0,
  totalReceived: 0,
  latestTimestamp: null,
  capacity: 0,
};

export function useTelemetryStore(): TelemetryStore {
  const services = useContext(TelemetryServicesContext);
  if (!services) throw new Error("useTelemetryStore must be used within DataProvider");
  return services.store;
}

export function useTelemetrySnapshot(): TelemetrySnapshot {
  const store = useTelemetryStore();
  return useSyncExternalStore(
    (listener) => store.subscribe(listener),
    () => store.getSnapshot(),
    () => emptySnapshot,
  );
}
