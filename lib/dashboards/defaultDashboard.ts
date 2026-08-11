import type { DashboardConfig } from "./types";

export const DEFAULT_DASHBOARD_ID = "system-default";

export const defaultDashboard: DashboardConfig = {
  id: DEFAULT_DASHBOARD_ID,
  name: "Default Observa",
  description: "Built-in live telemetry view",
  system: true,
  widgets: [
    { id: "default-line", dashboardId: DEFAULT_DASHBOARD_ID, title: "Latency over time", type: "line", metric: "latency", aggregation: "avg", bucket: "1m", timeRange: "15m", position: 0, width: 2, height: 1 },
    { id: "default-bar", dashboardId: DEFAULT_DASHBOARD_ID, title: "Throughput by service", type: "bar", metric: "throughput", aggregation: "avg", bucket: "raw", timeRange: "15m", position: 1, width: 1, height: 1 },
    { id: "default-scatter", dashboardId: DEFAULT_DASHBOARD_ID, title: "Payload size vs latency", type: "scatter", metric: "payloadSize", aggregation: "raw", bucket: "raw", timeRange: "15m", position: 2, width: 1, height: 1 },
    { id: "default-heatmap", dashboardId: DEFAULT_DASHBOARD_ID, title: "Service latency heatmap", type: "heatmap", metric: "latency", aggregation: "avg", bucket: "1m", timeRange: "15m", position: 3, width: 2, height: 1 },
  ],
};
