"use client";

import { SERVICES, type AggregationMode, type CapacityPreset, type ServiceName } from "@/lib/types";
import { useDataStream } from "@/hooks/useDataStream";

const capacities: CapacityPreset[] = [10000, 50000, 100000];
const batchSizes = [1, 10, 50, 100];
const modes: AggregationMode[] = ["raw", "1min", "5min", "1hour"];

export function FilterPanel() {
  const stream = useDataStream();
  return (
    <section className="panel control-panel">
      <h2>Stream controls</h2>
      <label>Capacity
        <select value={stream.capacity} onChange={(event) => stream.setCapacity(Number(event.target.value) as CapacityPreset)}>
          {capacities.map((capacity) => <option key={capacity} value={capacity}>{capacity.toLocaleString("en-US")}</option>)}
        </select>
      </label>
      <label>Batch size
        <select value={stream.batchSize} onChange={(event) => stream.setBatchSize(Number(event.target.value))}>
          {batchSizes.map((size) => <option key={size} value={size}>{size}</option>)}
        </select>
      </label>
      <label>Aggregation
        <select value={stream.aggregation} onChange={(event) => stream.setAggregation(event.target.value as AggregationMode)}>
          {modes.map((mode) => <option key={mode} value={mode}>{mode}</option>)}
        </select>
      </label>
      <label>Service
        <select value={stream.serviceFilter} onChange={(event) => stream.setServiceFilter(event.target.value as ServiceName | "all")}>
          <option value="all">All services</option>
          {SERVICES.map((service) => <option key={service} value={service}>{service}</option>)}
        </select>
      </label>
      <button type="button" className="danger" onClick={stream.stressMode}>Stress mode</button>
    </section>
  );
}
