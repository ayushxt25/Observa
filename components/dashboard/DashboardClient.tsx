"use client";

import { DataProvider } from "@/components/providers/DataProvider";
import { BarChart } from "@/components/charts/BarChart";
import { Heatmap } from "@/components/charts/Heatmap";
import { LineChart } from "@/components/charts/LineChart";
import { ScatterPlot } from "@/components/charts/ScatterPlot";
import { FilterPanel } from "@/components/controls/FilterPanel";
import { TimeRangeSelector } from "@/components/controls/TimeRangeSelector";
import { DataTable } from "@/components/ui/DataTable";
import { PerformanceMonitor } from "@/components/ui/PerformanceMonitor";
import { DashboardHeader } from "./DashboardHeader";
import { MetricCards } from "./MetricCards";
import { useDataStream } from "@/hooks/useDataStream";
import type { TelemetryPoint } from "@/lib/types";

function DashboardSurface() {
  const stream = useDataStream();
  return (
    <main className="dashboard-page">
      <DashboardHeader />
      <MetricCards />
      <section className="controls-grid">
        <FilterPanel />
        <TimeRangeSelector />
        <PerformanceMonitor />
      </section>
      <section className="charts-grid">
        <article className="panel chart-card wide">
          <h2>Latency over time</h2>
          <LineChart points={stream.aggregatedPoints} />
        </article>
        <article className="panel chart-card">
          <h2>Throughput by service</h2>
          <BarChart points={stream.visiblePoints} />
        </article>
        <article className="panel chart-card">
          <h2>Payload size vs latency</h2>
          <ScatterPlot points={stream.visiblePoints} />
        </article>
        <article className="panel chart-card wide">
          <h2>Service latency heatmap</h2>
          <Heatmap cells={stream.heatmap} />
        </article>
      </section>
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
