"use client";

import { createContext, useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useAuth } from "@/components/providers/AuthProvider";
import { generateInitialTelemetry } from "@/lib/dataGenerator";
import { markInteractionStart } from "@/lib/performance/marks";
import { createTelemetrySource } from "@/lib/telemetry/sourceFactory";
import { TelemetryStore } from "@/lib/telemetry/store";
import { TelemetryWorkerClient } from "@/lib/workers/telemetryWorkerClient";
import { SERVICES, type AggregationMode, type CapacityPreset, type InteractionType, type ServiceName, type TelemetryPoint, type TelemetrySourceKind, type TelemetrySourceStatus, type TimeRange } from "@/lib/types";
import type { TelemetrySource } from "@/lib/telemetry/source";

export interface DashboardControls {
  isPaused: boolean;
  capacity: CapacityPreset;
  batchSize: number;
  aggregation: AggregationMode;
  serviceFilter: ServiceName | "all";
  timeRange: TimeRange;
  sourceKind: TelemetrySourceKind;
  sourceStatus: TelemetrySourceStatus;
  availableServices: ServiceName[];
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
  setSourceKind: (kind: TelemetrySourceKind) => void;
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

function initialStatus(kind: TelemetrySourceKind, generated: number): TelemetrySourceStatus {
  return { kind, running: false, paused: false, intervalMs: kind === "simulation" ? 100 : 5000, batchSize: kind === "simulation" ? 10 : 0, generated, state: "idle" };
}

function sameStatus(left: TelemetrySourceStatus, right: TelemetrySourceStatus): boolean {
  return left.kind === right.kind &&
    left.running === right.running &&
    left.paused === right.paused &&
    left.intervalMs === right.intervalMs &&
    left.batchSize === right.batchSize &&
    left.generated === right.generated &&
    left.state === right.state &&
    left.message === right.message;
}

export function DataProvider({ initialData, children }: Props & { children: ReactNode }) {
  const { activeWorkspace } = useAuth();
  const [controls, setControls] = useState<DashboardControls>({
    isPaused: false,
    capacity: 10000,
    batchSize: 10,
    aggregation: "raw",
    serviceFilter: "all",
    timeRange: "15m",
    sourceKind: "simulation",
    sourceStatus: initialStatus("simulation", initialData.length),
    availableServices: [...SERVICES],
  });

  const [store] = useState(() => new TelemetryStore(10000, initialData));
  const [workerClient] = useState(() => new TelemetryWorkerClient());
  const sourceRef = useRef<TelemetrySource>(createTelemetrySource("simulation", { initialData, batchSize: 10 }));
  const cleanupSourceRef = useRef<() => void>(() => undefined);
  const sourceTokenRef = useRef(0);
  const activeInteractionRef = useRef<{ type: InteractionType; start: number } | null>(null);
  const controlsRef = useRef(controls);
  const workspaceRef = useRef(activeWorkspace?.id ?? null);

  useEffect(() => {
    controlsRef.current = controls;
  }, [controls]);

  const startSource = useCallback((source: TelemetrySource) => {
    sourceTokenRef.current += 1;
    const token = sourceTokenRef.current;
    cleanupSourceRef.current();
    sourceRef.current = source;
    const unsubscribe = source.subscribe((batch) => store.appendBatch(batch));
    void source.start();
    const updateStatus = () => setControls((current) => {
      if (sourceTokenRef.current !== token) return current;
      const sourceStatus = source.getStatus();
      return sameStatus(current.sourceStatus, sourceStatus) ? current : { ...current, sourceStatus };
    });
    const statusTimer = setInterval(updateStatus, 1000);
    updateStatus();
    void Promise.resolve(source.getServices?.() ?? []).then((services) => {
      setControls((current) => {
        if (sourceTokenRef.current !== token) return current;
        return current.availableServices.join("\0") === services.join("\0") ? current : { ...current, availableServices: services };
      });
    }).catch((error) => {
      setControls((current) => sourceTokenRef.current === token ? { ...current, sourceStatus: { ...source.getStatus(), state: "degraded", message: error instanceof Error ? error.message : "Service discovery failed" } } : current);
    });
    cleanupSourceRef.current = () => {
      clearInterval(statusTimer);
      unsubscribe();
      void source.stop();
    };
  }, [store]);

  useEffect(() => {
    startSource(sourceRef.current);
    return () => {
      cleanupSourceRef.current();
      workerClient.terminate();
    };
  }, [startSource, workerClient]);

  const markInteraction = useCallback((type: InteractionType) => {
    activeInteractionRef.current = markInteractionStart(type);
  }, []);

  const pause = useCallback(() => {
    sourceRef.current.pause?.();
    setControls((current) => ({ ...current, isPaused: true, sourceStatus: sourceRef.current.getStatus() }));
  }, []);

  const resume = useCallback(() => {
    sourceRef.current.resume?.();
    setControls((current) => ({ ...current, isPaused: false, sourceStatus: sourceRef.current.getStatus() }));
  }, []);

  const reset = useCallback(() => {
    const capacity = store.getSnapshot().capacity as CapacityPreset;
    if (sourceRef.current.kind === "remote") {
      store.reset([], capacity);
      sourceRef.current.reset?.();
      return;
    }
    const fresh = generateInitialTelemetry(Math.min(capacity, 10000), 42);
    store.reset(fresh.points, capacity);
    sourceRef.current.reset?.(42, fresh.state.timestamp, fresh.state.sequence, fresh.points.length);
  }, [store]);

  const setCapacity = useCallback((capacity: CapacityPreset) => {
    store.setCapacity(capacity);
    setControls((current) => ({ ...current, capacity }));
  }, [store]);

  const setBatchSize = useCallback((batchSize: number) => {
    sourceRef.current.setBatchSize?.(batchSize);
    setControls((current) => ({ ...current, batchSize, sourceStatus: sourceRef.current.getStatus() }));
  }, []);

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

  const setSourceKind = useCallback((sourceKind: TelemetrySourceKind) => {
    const current = controlsRef.current;
    if (current.sourceKind === sourceKind) return;
    const capacity = store.getSnapshot().capacity as CapacityPreset;
    const nextSource = createTelemetrySource(sourceKind, { initialData, batchSize: current.batchSize });
    store.reset(sourceKind === "simulation" ? initialData.slice(-capacity) : [], capacity);
    setControls((state) => ({
      ...state,
      sourceKind,
      isPaused: false,
      serviceFilter: "all",
      availableServices: sourceKind === "simulation" ? [...SERVICES] : [],
      sourceStatus: initialStatus(sourceKind, sourceKind === "simulation" ? initialData.length : 0),
    }));
    startSource(nextSource);
  }, [initialData, startSource, store]);

  useEffect(() => {
    const nextWorkspace = activeWorkspace?.id ?? null;
    if (workspaceRef.current === nextWorkspace) return;
    workspaceRef.current = nextWorkspace;
    if (controlsRef.current.sourceKind !== "remote") return;
    const capacity = store.getSnapshot().capacity as CapacityPreset;
    const nextSource = createTelemetrySource("remote", { initialData, batchSize: controlsRef.current.batchSize });
    store.reset([], capacity);
    setControls((state) => ({
      ...state,
      serviceFilter: "all",
      availableServices: [],
      sourceStatus: initialStatus("remote", 0),
    }));
    startSource(nextSource);
  }, [activeWorkspace?.id, initialData, startSource, store]);

  const stressMode = useCallback(() => {
    markInteraction("stress");
    if (sourceRef.current.kind === "remote") {
      sourceRef.current.reset?.();
      return;
    }
    const capacity = store.getSnapshot().capacity as CapacityPreset;
    const fresh = generateInitialTelemetry(capacity, 4242);
    store.reset(fresh.points, capacity);
    sourceRef.current.reset?.(4242, fresh.state.timestamp, fresh.state.sequence, fresh.points.length);
  }, [markInteraction, store]);

  const actions = useMemo<TelemetryActions>(() => ({
    pause,
    resume,
    reset,
    setCapacity,
    setBatchSize,
    setAggregation,
    setServiceFilter,
    setTimeRange,
    setSourceKind,
    stressMode,
    markInteraction,
  }), [markInteraction, pause, reset, resume, setAggregation, setBatchSize, setCapacity, setServiceFilter, setSourceKind, setTimeRange, stressMode]);

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
