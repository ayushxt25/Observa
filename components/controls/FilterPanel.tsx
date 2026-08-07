"use client";

import { useTransition } from "react";
import { SERVICES, type AggregationMode, type CapacityPreset, type ServiceName } from "@/lib/types";
import { useDashboardControls, useTelemetryActions } from "@/hooks/useDashboardControls";

const capacities: CapacityPreset[] = [10000, 50000, 100000];
const batchSizes = [1, 10, 50, 100];
const modes: AggregationMode[] = ["raw", "1min", "5min", "1hour"];

export function FilterPanel() {
  const controls = useDashboardControls();
  const actions = useTelemetryActions();
  const [isPending, startTransition] = useTransition();
  return (
    <section className="panel control-panel">
      <h2>Stream controls {isPending ? <span className="pending-badge">Applying...</span> : null}</h2>
      <label>Capacity
        <select aria-label="Retained point capacity" value={controls.capacity} onChange={(event) => actions.setCapacity(Number(event.target.value) as CapacityPreset)}>
          {capacities.map((capacity) => <option key={capacity} value={capacity}>{capacity.toLocaleString("en-US")}</option>)}
        </select>
      </label>
      <label>Batch size
        <select aria-label="Generated batch size" value={controls.batchSize} onChange={(event) => actions.setBatchSize(Number(event.target.value))}>
          {batchSizes.map((size) => <option key={size} value={size}>{size}</option>)}
        </select>
      </label>
      <label>Aggregation
        <select
          aria-label="Latency aggregation mode"
          value={controls.aggregation}
          onChange={(event) => {
            const value = event.target.value as AggregationMode;
            startTransition(() => actions.setAggregation(value));
          }}
        >
          {modes.map((mode) => <option key={mode} value={mode}>{mode}</option>)}
        </select>
      </label>
      <label>Service
        <select
          aria-label="Service filter"
          value={controls.serviceFilter}
          onChange={(event) => {
            const value = event.target.value as ServiceName | "all";
            startTransition(() => actions.setServiceFilter(value));
          }}
        >
          <option value="all">All services</option>
          {SERVICES.map((service) => <option key={service} value={service}>{service}</option>)}
        </select>
      </label>
      <button type="button" className="danger" aria-label="Activate stress test mode" onClick={() => startTransition(actions.stressMode)}>Stress mode</button>
    </section>
  );
}
