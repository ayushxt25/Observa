"use client";

import { createContext, useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { aggregateLatency, buildHeatmap, filterTelemetry, summarize } from "@/lib/aggregation";
import { generateInitialTelemetry, generateTelemetryBatch, type GeneratorState } from "@/lib/dataGenerator";
import { RingBuffer } from "@/lib/ringBuffer";
import type {
  AggregatedPoint,
  AggregationMode,
  CapacityPreset,
  HeatmapCell,
  MetricSummary,
  ServiceName,
  TelemetryPoint,
  TimeRange,
  WorkerRequest,
  WorkerResponse,
} from "@/lib/types";

interface DataContextValue {
  isPaused: boolean;
  capacity: CapacityPreset;
  batchSize: number;
  aggregation: AggregationMode;
  serviceFilter: ServiceName | "all";
  timeRange: TimeRange;
  version: number;
  tableVersion: number;
  summary: MetricSummary;
  visiblePoints: TelemetryPoint[];
  aggregatedPoints: AggregatedPoint[];
  heatmap: HeatmapCell[];
  getSnapshot: () => TelemetryPoint[];
  pause: () => void;
  resume: () => void;
  reset: () => void;
  setCapacity: (capacity: CapacityPreset) => void;
  setBatchSize: (batchSize: number) => void;
  setAggregation: (aggregation: AggregationMode) => void;
  setServiceFilter: (service: ServiceName | "all") => void;
  setTimeRange: (range: TimeRange) => void;
  stressMode: () => void;
}

export const DataContext = createContext<DataContextValue | null>(null);

interface Props {
  initialData: TelemetryPoint[];
}

export function DataProvider({ initialData, children }: Props & { children: ReactNode }) {
  const [isPaused, setIsPaused] = useState(false);
  const [capacity, setCapacityState] = useState<CapacityPreset>(10000);
  const [batchSize, setBatchSizeState] = useState(10);
  const [aggregation, setAggregation] = useState<AggregationMode>("raw");
  const [serviceFilter, setServiceFilter] = useState<ServiceName | "all">("all");
  const [timeRange, setTimeRange] = useState<TimeRange>("15m");
  const [version, setVersion] = useState(0);
  const [tableVersion, setTableVersion] = useState(0);
  const [summary, setSummary] = useState<MetricSummary>(() => summarize(initialData, initialData.length));
  const [visiblePoints, setVisiblePoints] = useState<TelemetryPoint[]>(() => filterTelemetry(initialData, "all", "15m"));
  const [aggregatedPoints, setAggregatedPoints] = useState<AggregatedPoint[]>(() => aggregateLatency(visiblePoints, "raw"));
  const [heatmap, setHeatmap] = useState<HeatmapCell[]>(() => buildHeatmap(visiblePoints));

  const bufferRef = useRef(new RingBuffer<TelemetryPoint>(10000, initialData));
  const generatorRef = useRef<GeneratorState>({ seed: 42, sequence: initialData.length, timestamp: initialData.at(-1)?.timestamp ?? 0 });
  const pausedRef = useRef(isPaused);
  const batchRef = useRef(batchSize);
  const generatedRef = useRef(initialData.length);
  const notifyTimerRef = useRef<number | null>(null);
  const tableTimerRef = useRef<number | null>(null);
  const workerRef = useRef<Worker | null>(null);
  const requestIdRef = useRef(0);

  useEffect(() => {
    pausedRef.current = isPaused;
  }, [isPaused]);

  useEffect(() => {
    batchRef.current = batchSize;
  }, [batchSize]);

  const getSnapshot = useCallback(() => bufferRef.current.toArray(), []);

  const recompute = useCallback(() => {
    const points = getSnapshot();
    setSummary(summarize(points, generatedRef.current));
    const filtered = filterTelemetry(points, serviceFilter, timeRange);
    setVisiblePoints(filtered);

    if (typeof Worker === "undefined") {
      setAggregatedPoints(aggregateLatency(filtered, aggregation));
      setHeatmap(buildHeatmap(filtered));
      return;
    }

    if (!workerRef.current) {
      workerRef.current = new Worker(new URL("../../workers/data.worker.ts", import.meta.url));
      workerRef.current.onmessage = (event: MessageEvent<WorkerResponse>) => {
        if (event.data.id !== requestIdRef.current) return;
        setAggregatedPoints(event.data.points);
        setHeatmap(event.data.heatmap);
      };
    }
    const id = requestIdRef.current + 1;
    requestIdRef.current = id;
    const request: WorkerRequest = { id, type: "aggregate", points, mode: aggregation, service: serviceFilter, timeRange, capacity };
    workerRef.current.postMessage(request);
  }, [aggregation, capacity, getSnapshot, serviceFilter, timeRange]);

  const scheduleNotify = useCallback(() => {
    if (notifyTimerRef.current !== null) return;
    notifyTimerRef.current = window.setTimeout(() => {
      notifyTimerRef.current = null;
      setVersion((current) => current + 1);
      recompute();
    }, 250);
  }, [recompute]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      if (pausedRef.current) return;
      const result = generateTelemetryBatch(generatorRef.current, batchRef.current, 100);
      generatorRef.current = result.state;
      generatedRef.current += result.points.length;
      bufferRef.current.pushMany(result.points);
      scheduleNotify();
    }, 100);
    return () => window.clearInterval(timer);
  }, [scheduleNotify]);

  useEffect(() => {
    recompute();
  }, [recompute]);

  useEffect(() => {
    tableTimerRef.current = window.setInterval(() => setTableVersion((current) => current + 1), 1000);
    return () => {
      if (tableTimerRef.current !== null) window.clearInterval(tableTimerRef.current);
      if (notifyTimerRef.current !== null) window.clearTimeout(notifyTimerRef.current);
      workerRef.current?.terminate();
    };
  }, []);

  const reset = useCallback(() => {
    const fresh = generateInitialTelemetry(Math.min(capacity, 10000), 42);
    bufferRef.current = new RingBuffer<TelemetryPoint>(capacity, fresh.points);
    generatorRef.current = fresh.state;
    generatedRef.current = fresh.points.length;
    setVersion((current) => current + 1);
    recompute();
  }, [capacity, recompute]);

  const setCapacity = useCallback((next: CapacityPreset) => {
    bufferRef.current = bufferRef.current.resize(next);
    setCapacityState(next);
    setVersion((current) => current + 1);
  }, []);

  const stressMode = useCallback(() => {
    const fresh = generateInitialTelemetry(capacity, 4242);
    bufferRef.current = new RingBuffer<TelemetryPoint>(capacity, fresh.points);
    generatorRef.current = fresh.state;
    generatedRef.current += fresh.points.length;
    setVersion((current) => current + 1);
    recompute();
  }, [capacity, recompute]);

  const value = useMemo<DataContextValue>(
    () => ({
      isPaused,
      capacity,
      batchSize,
      aggregation,
      serviceFilter,
      timeRange,
      version,
      tableVersion,
      summary,
      visiblePoints,
      aggregatedPoints,
      heatmap,
      getSnapshot,
      pause: () => setIsPaused(true),
      resume: () => setIsPaused(false),
      reset,
      setCapacity,
      setBatchSize: setBatchSizeState,
      setAggregation,
      setServiceFilter,
      setTimeRange,
      stressMode,
    }),
    [aggregation, aggregatedPoints, batchSize, capacity, getSnapshot, heatmap, isPaused, reset, serviceFilter, setCapacity, summary, tableVersion, timeRange, version, visiblePoints, stressMode],
  );

  return <DataContext.Provider value={value}>{children}</DataContext.Provider>;
}
