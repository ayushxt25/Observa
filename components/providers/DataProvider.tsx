"use client";

import { createContext, useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { generateInitialTelemetry } from "@/lib/dataGenerator";
import { markInteractionStart } from "@/lib/performance/marks";
import { SimulationTelemetrySource } from "@/lib/telemetry/source";
import { TelemetryStore } from "@/lib/telemetry/store";
import { TelemetryWorkerClient } from "@/lib/workers/telemetryWorkerClient";
import type { AggregationMode, CapacityPreset, InteractionType, ServiceName, TelemetryPoint, TimeRange } from "@/lib/types";

export interface DashboardControls {
  isPaused: boolean;
  capacity: CapacityPreset;
  batchSize: number;
  aggregation: AggregationMode;
  serviceFilter: ServiceName | "all";
  timeRange: TimeRange;
}

export interface TelemetryActions {
  pause: () => void;
  resume: () => void;
  reset: () => void;
  setCapacity: (capacity: CapacityPreset) => void;
  setBatchSize: (batchSize: number) => void;
  setAggregation: (aggregation: AggregationMode) => void;
  setServiceFilter: (service: ServiceName | "all") => void;
  setTimeRange: (range: TimeRange) => void;
  stressMode: () => void;
  markInteraction: (type: InteractionType) => void;
}

export interface TelemetryServices {
  store: TelemetryStore;
  workerClient: TelemetryWorkerClient;
  getActiveInteraction: () => { type: InteractionType; start: number } | null;
  clearActiveInteraction: () => void;
}

export const DashboardControlsContext = createContext<DashboardControls | null>(null);
export const TelemetryActionsContext = createContext<TelemetryActions | null>(null);
export const TelemetryServicesContext = createContext<TelemetryServices | null>(null);

interface Props {
  initialData: TelemetryPoint[];
}

export function DataProvider({ initialData, children }: Props & { children: ReactNode }) {
  const [controls, setControls] = useState<DashboardControls>({
    isPaused: false,
    capacity: 10000,
    batchSize: 10,
    aggregation: "raw",
    serviceFilter: "all",
    timeRange: "15m",
  });

  const [store] = useState(() => new TelemetryStore(10000, initialData));
  const [source] = useState(() => new SimulationTelemetrySource({
    seed: 42,
    intervalMs: 100,
    batchSize: 10,
    startTimestamp: initialData.at(-1)?.timestamp ?? 0,
    initialSequence: initialData.length,
    generated: initialData.length,
  }));
  const [workerClient] = useState(() => new TelemetryWorkerClient());
  const activeInteractionRef = useRef<{ type: InteractionType; start: number } | null>(null);
  useEffect(() => {
    const unsubscribe = source.subscribe((batch) => store.appendBatch(batch));
    source.start();
    return () => {
      unsubscribe();
      source.stop();
      workerClient.terminate();
    };
  }, [source, store, workerClient]);

  const markInteraction = useCallback((type: InteractionType) => {
    activeInteractionRef.current = markInteractionStart(type);
  }, []);

  const pause = useCallback(() => {
    source.pause();
    setControls((current) => ({ ...current, isPaused: true }));
  }, [source]);

  const resume = useCallback(() => {
    source.resume();
    setControls((current) => ({ ...current, isPaused: false }));
  }, [source]);

  const reset = useCallback(() => {
    const capacity = store.getSnapshot().capacity as CapacityPreset;
    const fresh = generateInitialTelemetry(Math.min(capacity, 10000), 42);
    store.reset(fresh.points, capacity);
    source.reset(42, fresh.state.timestamp, fresh.state.sequence, fresh.points.length);
  }, [source, store]);

  const setCapacity = useCallback((capacity: CapacityPreset) => {
    store.setCapacity(capacity);
    setControls((current) => ({ ...current, capacity }));
  }, [store]);

  const setBatchSize = useCallback((batchSize: number) => {
    source.setBatchSize(batchSize);
    setControls((current) => ({ ...current, batchSize }));
  }, [source]);

  const setAggregation = useCallback((aggregation: AggregationMode) => {
    markInteraction("aggregation");
    setControls((current) => ({ ...current, aggregation }));
  }, [markInteraction]);

  const setServiceFilter = useCallback((serviceFilter: ServiceName | "all") => {
    markInteraction("filter");
    setControls((current) => ({ ...current, serviceFilter }));
  }, [markInteraction]);

  const setTimeRange = useCallback((timeRange: TimeRange) => {
    markInteraction("time-range");
    setControls((current) => ({ ...current, timeRange }));
  }, [markInteraction]);

  const stressMode = useCallback(() => {
    markInteraction("stress");
    const capacity = store.getSnapshot().capacity as CapacityPreset;
    const fresh = generateInitialTelemetry(capacity, 4242);
    store.reset(fresh.points, capacity);
    source.reset(4242, fresh.state.timestamp, fresh.state.sequence, fresh.points.length);
  }, [markInteraction, source, store]);

  const actions = useMemo<TelemetryActions>(() => ({
    pause,
    resume,
    reset,
    setCapacity,
    setBatchSize,
    setAggregation,
    setServiceFilter,
    setTimeRange,
    stressMode,
    markInteraction,
  }), [markInteraction, pause, reset, resume, setAggregation, setBatchSize, setCapacity, setServiceFilter, setTimeRange, stressMode]);

  const services = useMemo<TelemetryServices>(() => ({
    store,
    workerClient,
    getActiveInteraction: () => activeInteractionRef.current,
    clearActiveInteraction: () => {
      activeInteractionRef.current = null;
    },
  }), [store, workerClient]);

  return (
    <TelemetryServicesContext.Provider value={services}>
      <DashboardControlsContext.Provider value={controls}>
        <TelemetryActionsContext.Provider value={actions}>{children}</TelemetryActionsContext.Provider>
      </DashboardControlsContext.Provider>
    </TelemetryServicesContext.Provider>
  );
}
