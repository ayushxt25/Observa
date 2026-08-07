"use client";

import { useContext, useEffect, useMemo, useState } from "react";
import { TelemetryServicesContext } from "@/components/providers/DataProvider";
import { markInteractionEnd } from "@/lib/performance/marks";
import { filterTelemetry, summarize } from "@/lib/telemetry/query";
import { useDashboardControls } from "./useDashboardControls";
import { useTelemetrySnapshot, useTelemetryStore } from "./useTelemetryStore";
import type { AggregatedPoint, HeatmapCell, InteractionMetric, MetricSummary, TelemetryPoint } from "@/lib/types";

export interface TelemetryQueryResult {
  snapshotVersion: number;
  summary: MetricSummary;
  visiblePoints: TelemetryPoint[];
  aggregatedPoints: AggregatedPoint[];
  heatmap: HeatmapCell[];
  dataProcessingDurationMs: number;
  latestInteraction: InteractionMetric | null;
}

export function useTelemetryQuery(): TelemetryQueryResult {
  const services = useContext(TelemetryServicesContext);
  if (!services) throw new Error("useTelemetryQuery must be used within DataProvider");
  const store = useTelemetryStore();
  const snapshot = useTelemetrySnapshot();
  const snapshotVersion = snapshot.version;
  const controls = useDashboardControls();
  const [workerData, setWorkerData] = useState<{ points: AggregatedPoint[]; heatmap: HeatmapCell[]; processingStartedAt: number }>({ points: [], heatmap: [], processingStartedAt: 0 });
  const [dataProcessingDurationMs, setDataProcessingDurationMs] = useState(0);
  const [latestInteraction, setLatestInteraction] = useState<InteractionMetric | null>(null);

  const points = useMemo(() => {
    void snapshotVersion;
    return store.readAll();
  }, [snapshotVersion, store]);
  const visiblePoints = useMemo(() => filterTelemetry(points, controls.serviceFilter, controls.timeRange), [controls.serviceFilter, controls.timeRange, points]);
  const summary = useMemo(() => summarize(points, snapshot.totalReceived), [points, snapshot.totalReceived]);

  useEffect(() => {
    const processingStartedAt = performance.now();
    let active = true;
    void services.workerClient.aggregate({
      points,
      mode: controls.aggregation,
      service: controls.serviceFilter,
      timeRange: controls.timeRange,
      capacity: controls.capacity,
      processingStartedAt,
    }).then((result) => {
      if (!active) return;
      setWorkerData({ points: result.points, heatmap: result.heatmap, processingStartedAt: result.processingStartedAt });
      setDataProcessingDurationMs(performance.now() - result.processingStartedAt);
      const interaction = services.getActiveInteraction();
      if (interaction) {
        setLatestInteraction(markInteractionEnd(interaction));
        services.clearActiveInteraction();
      }
    });
    return () => {
      active = false;
    };
  }, [controls.aggregation, controls.capacity, controls.serviceFilter, controls.timeRange, points, services]);

  return {
    snapshotVersion,
    summary,
    visiblePoints,
    aggregatedPoints: workerData.points,
    heatmap: workerData.heatmap,
    dataProcessingDurationMs,
    latestInteraction,
  };
}
