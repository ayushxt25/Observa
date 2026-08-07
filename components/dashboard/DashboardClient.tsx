"use client";

import { lazy, memo, Suspense } from "react";
import { DataProvider } from "@/components/providers/DataProvider";
import { BarChart } from "@/components/charts/BarChart";
import { Heatmap } from "@/components/charts/Heatmap";
import { LineChart } from "@/components/charts/LineChart";
import { ScatterPlot } from "@/components/charts/ScatterPlot";
import { FilterPanel } from "@/components/controls/FilterPanel";
import { TimeRangeSelector } from "@/components/controls/TimeRangeSelector";
import { DataTable } from "@/components/ui/DataTable";
import { DashboardHeader } from "./DashboardHeader";
import { MetricCards } from "./MetricCards";
import { useTelemetryQuery } from "@/hooks/useTelemetryQuery";
import type { TelemetryPoint } from "@/lib/types";

const PerformanceMonitor = lazy(() =>
  import("@/components/ui/PerformanceMonitor").then((module) => ({
    default: module.PerformanceMonitor,
  })),
);

const ChartGrid = memo(function ChartGrid() {
  const telemetry = useTelemetryQuery();
  return (
    <section className="charts-grid">
      <article className="panel chart-card wide">
        <h2>Latency over time</h2>
        <LineChart points={telemetry.aggregatedPoints} />
      </article>
      <article className="panel chart-card">
        <h2>Throughput by service</h2>
        <BarChart points={telemetry.visiblePoints} />
      </article>
      <article className="panel chart-card">
        <h2>Payload size vs latency</h2>
        <ScatterPlot points={telemetry.visiblePoints} />
      </article>
      <article className="panel chart-card wide">
        <h2>Service latency heatmap</h2>
        <Heatmap cells={telemetry.heatmap} />
      </article>
    </section>
  );
});

function DashboardSurface() {
  return (
    <main className="dashboard-page">
      <DashboardHeader />
      <MetricCards />
      <section className="controls-grid">
        <FilterPanel />
        <TimeRangeSelector />
        <Suspense fallback={<section className="panel perf-panel"><h2>Performance</h2><span>Loading monitor...</span></section>}>
          <PerformanceMonitor />
        </Suspense>
      </section>
      <ChartGrid />
      <section className="panel">
        <div className="section-heading">
          <h2>Raw telemetry</h2>
          <span>Reduced-cadence virtualized table</span>
        </div>
        <DataTable />
      </section>
    </main>
  );
}

export function DashboardClient({ initialData }: { initialData: TelemetryPoint[] }) {
  return (
    <DataProvider initialData={initialData}>
      <DashboardSurface />
    </DataProvider>
  );
}
