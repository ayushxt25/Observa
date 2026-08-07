"use client";

import { memo } from "react";
import { usePerformanceMonitor } from "@/hooks/usePerformanceMonitor";
import { useDashboardControls } from "@/hooks/useDashboardControls";
import { useTelemetryQuery } from "@/hooks/useTelemetryQuery";

export const PerformanceMonitor = memo(function PerformanceMonitor() {
  const { capacity } = useDashboardControls();
  const { summary, dataProcessingDurationMs, latestInteraction } = useTelemetryQuery();
  const { fps, frameMs, chartRenderMs, longTasks, heap } = usePerformanceMonitor();

  return (
    <section className="panel perf-panel">
      <h2>Performance</h2>
      <span>FPS <strong>{fps}</strong></span>
      <span>Retained <strong>{summary.totalPoints.toLocaleString()}</strong></span>
      <span>Generated <strong>{summary.generatedPoints.toLocaleString()}</strong></span>
      <span>Capacity <strong>{capacity.toLocaleString()}</strong></span>
      <span>Heap <strong>{heap}</strong></span>
      <span>Long tasks <strong>{longTasks}</strong></span>
      <span>Frame avg <strong>{frameMs.toFixed(1)} ms</strong></span>
      <span>Chart render <strong>{chartRenderMs.toFixed(1)} ms</strong></span>
      <span>Data processing <strong>{dataProcessingDurationMs.toFixed(1)} ms</strong></span>
      <span>Interaction <strong>{latestInteraction ? `${latestInteraction.type} ${latestInteraction.durationMs.toFixed(1)} ms` : "Not measured"}</strong></span>
    </section>
  );
});
