"use client";

import { lazy, memo, Suspense } from "react";
import { DashboardConfigProvider } from "@/components/providers/DashboardConfigProvider";
import { DataProvider } from "@/components/providers/DataProvider";
import { AuthProvider } from "@/components/providers/AuthProvider";
import { AuthGate } from "@/components/auth/AuthGate";
import { WorkspaceSwitcher } from "@/components/auth/WorkspaceSwitcher";
import { FilterPanel } from "@/components/controls/FilterPanel";
import { TimeRangeSelector } from "@/components/controls/TimeRangeSelector";
import { DataTable } from "@/components/ui/DataTable";
import { DashboardSelector } from "./DashboardSelector";
import { DashboardWidgetGrid } from "./DashboardWidgetRenderer";
import { AlertsPanel } from "./AlertsPanel";
import { DashboardHeader } from "./DashboardHeader";
import { MetricCards } from "./MetricCards";
import type { TelemetryPoint } from "@/lib/types";

const PerformanceMonitor = lazy(() =>
  import("@/components/ui/PerformanceMonitor").then((module) => ({
    default: module.PerformanceMonitor,
  })),
);

const ChartGrid = memo(DashboardWidgetGrid);

function DashboardSurface() {
  return (
    <main className="dashboard-page">
      <DashboardHeader />
      <WorkspaceSwitcher />
      <MetricCards />
      <section className="controls-grid">
        <FilterPanel />
        <TimeRangeSelector />
        <Suspense fallback={<section className="panel perf-panel"><h2>Performance</h2><span>Loading monitor...</span></section>}>
          <PerformanceMonitor />
        </Suspense>
      </section>
      <DashboardSelector />
      <AlertsPanel />
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
    <AuthProvider>
      <AuthGate>
        <DataProvider initialData={initialData}>
          <DashboardConfigProvider>
            <DashboardSurface />
          </DashboardConfigProvider>
        </DataProvider>
      </AuthGate>
    </AuthProvider>
  );
}
