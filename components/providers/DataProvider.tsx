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
  InteractionMetric,
  InteractionType,
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
  latestInteraction: InteractionMetric | null;
  dataProcessingDurationMs: number;
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
  const [latestInteraction, setLatestInteraction] = useState<InteractionMetric | null>(null);
  const [dataProcessingDurationMs, setDataProcessingDurationMs] = useState(0);

  const bufferRef = useRef(new RingBuffer<TelemetryPoint>(10000, initialData));
  const generatorRef = useRef<GeneratorState>({ seed: 42, sequence: initialData.length, timestamp: initialData.at(-1)?.timestamp ?? 0 });
  const pausedRef = useRef(isPaused);
  const batchRef = useRef(batchSize);
  const generatedRef = useRef(initialData.length);
  const notifyTimerRef = useRef<number | null>(null);
  const tableTimerRef = useRef<number | null>(null);
  const workerRef = useRef<Worker | null>(null);
  const requestIdRef = useRef(0);
  const activeInteractionRef = useRef<{ type: InteractionType; start: number } | null>(null);

  useEffect(() => {
    pausedRef.current = isPaused;
  }, [isPaused]);

  useEffect(() => {
    batchRef.current = batchSize;
  }, [batchSize]);

  const getSnapshot = useCallback(() => bufferRef.current.toArray(), []);

  const beginInteraction = useCallback((type: InteractionType) => {
    const start = performance.now();
    activeInteractionRef.current = { type, start };
    performance.mark(`pulsegrid:${type}:start`);
  }, []);

  const finishMeasurements = useCallback((processingStart: number) => {
    const processingDuration = performance.now() - processingStart;
    setDataProcessingDurationMs(processingDuration);
    const interaction = activeInteractionRef.current;
    if (!interaction) return;
    const endMark = `pulsegrid:${interaction.type}:end`;
    const measureName = `pulsegrid:${interaction.type}:latency`;
    performance.mark(endMark);
    performance.measure(measureName, `pulsegrid:${interaction.type}:start`, endMark);
    setLatestInteraction({ type: interaction.type, durationMs: performance.now() - interaction.start });
    performance.clearMarks(`pulsegrid:${interaction.type}:start`);
    performance.clearMarks(endMark);
    performance.clearMeasures(measureName);
    activeInteractionRef.current = null;
  }, []);

  const recompute = useCallback(() => {
    const processingStart = performance.now();
    const points = getSnapshot();
    setSummary(summarize(points, generatedRef.current));
    const filtered = filterTelemetry(points, serviceFilter, timeRange);
    setVisiblePoints(filtered);

    if (typeof Worker === "undefined") {
      setAggregatedPoints(aggregateLatency(filtered, aggregation));
      setHeatmap(buildHeatmap(filtered));
      finishMeasurements(processingStart);
      return;
    }

    if (!workerRef.current) {
      workerRef.current = new Worker(new URL("../../workers/data.worker.ts", import.meta.url));
      workerRef.current.onmessage = (event: MessageEvent<WorkerResponse>) => {
        if (event.data.id !== requestIdRef.current) return;
        setAggregatedPoints(event.data.points);
        setHeatmap(event.data.heatmap);
        finishMeasurements(event.data.processingStartedAt);
      };
    }
    const id = requestIdRef.current + 1;
    requestIdRef.current = id;
    const request: WorkerRequest = { id, type: "aggregate", points, mode: aggregation, service: serviceFilter, timeRange, capacity, processingStartedAt: processingStart };
    workerRef.current.postMessage(request);
  }, [aggregation, capacity, finishMeasurements, getSnapshot, serviceFilter, timeRange]);

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
    beginInteraction("stress");
    const fresh = generateInitialTelemetry(capacity, 4242);
    bufferRef.current = new RingBuffer<TelemetryPoint>(capacity, fresh.points);
    generatorRef.current = fresh.state;
    generatedRef.current += fresh.points.length;
    setVersion((current) => current + 1);
    recompute();
  }, [beginInteraction, capacity, recompute]);

  const changeAggregation = useCallback((next: AggregationMode) => {
    beginInteraction("aggregation");
    setAggregation(next);
  }, [beginInteraction]);

  const changeServiceFilter = useCallback((next: ServiceName | "all") => {
    beginInteraction("filter");
    setServiceFilter(next);
  }, [beginInteraction]);

  const changeTimeRange = useCallback((next: TimeRange) => {
    beginInteraction("time-range");
    setTimeRange(next);
  }, [beginInteraction]);

  const pause = useCallback(() => setIsPaused(true), []);
  const resume = useCallback(() => setIsPaused(false), []);
  const changeBatchSize = useCallback((next: number) => setBatchSizeState(next), []);

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
      latestInteraction,
      dataProcessingDurationMs,
      getSnapshot,
      pause,
      resume,
      reset,
      setCapacity,
      setBatchSize: changeBatchSize,
      setAggregation: changeAggregation,
      setServiceFilter: changeServiceFilter,
      setTimeRange: changeTimeRange,
      stressMode,
    }),
    [
      aggregation,
      aggregatedPoints,
      batchSize,
      capacity,
      changeAggregation,
      changeBatchSize,
      changeServiceFilter,
      changeTimeRange,
      dataProcessingDurationMs,
      getSnapshot,
      heatmap,
      isPaused,
      latestInteraction,
      pause,
      reset,
      resume,
      serviceFilter,
      setCapacity,
      stressMode,
      summary,
      tableVersion,
      timeRange,
      version,
      visiblePoints,
    ],
  );

  return <DataContext.Provider value={value}>{children}</DataContext.Provider>;
}
