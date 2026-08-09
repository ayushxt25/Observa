import { describe, expect, it } from "vitest";
import { mapApiDashboard, widgetToApiBody } from "@/lib/api/dashboards";
import { buildMetricQueryKey, QueryCache } from "@/lib/dashboards/queryCache";
import { evaluateThreshold } from "@/lib/dashboards/thresholds";
import { buildWidgetLine, filterWidgetPoints } from "@/lib/dashboards/widgetData";
import type { DashboardWidgetConfig } from "@/lib/dashboards/types";
import type { TelemetryPoint } from "@/lib/types";

const widget: DashboardWidgetConfig = {
  id: "w1",
  dashboardId: "d1",
  title: "Latency",
  type: "line",
  metric: "latency",
  aggregation: "avg",
  bucket: "1m",
  timeRange: "15m",
  position: 0,
  width: 2,
  height: 1,
  thresholdWarning: 100,
  thresholdCritical: 200,
};

const points: TelemetryPoint[] = [
  { id: "1", timestamp: 1_000, service: "api", region: "us", latency: 50, throughput: 10, cpuUsage: 20, memoryUsage: 30, errorRate: 0, payloadSize: 100, status: "healthy" },
  { id: "2", timestamp: 61_000, service: "api", region: "us", latency: 150, throughput: 20, cpuUsage: 30, memoryUsage: 40, errorRate: 1, payloadSize: 200, status: "degraded" },
  { id: "3", timestamp: 121_000, service: "worker", region: "eu", latency: 250, throughput: 30, cpuUsage: 40, memoryUsage: 50, errorRate: 2, payloadSize: 300, status: "critical" },
];

describe("dashboard DTO mapping", () => {
  it("maps backend dashboard widgets and sorts by position", () => {
    const dashboard = mapApiDashboard({
      id: "d1",
      name: "Ops",
      widgets: [
        { ...widget, position: 2, timeRange: "15m" },
        { ...widget, id: "w0", position: 0, timeRange: "5m", thresholdWarning: null, thresholdCritical: null },
      ],
    });
    expect(dashboard.system).toBe(false);
    expect(dashboard.widgets.map((item) => item.id)).toEqual(["w0", "w1"]);
    expect(dashboard.widgets[0].thresholdWarning).toBeUndefined();
  });
});

describe("threshold evaluation", () => {
  it("returns semantic threshold states", () => {
    expect(evaluateThreshold(50, widget)).toBe("normal");
    expect(evaluateThreshold(100, widget)).toBe("warning");
    expect(evaluateThreshold(200, widget)).toBe("critical");
  });
});

describe("widget API body mapping", () => {
  it("sends only editable fields and drops non-finite thresholds", () => {
    const body = widgetToApiBody({ ...widget, thresholdWarning: Number.NaN });
    expect(body).not.toHaveProperty("id");
    expect(body).not.toHaveProperty("dashboardId");
    expect(body.thresholdWarning).toBeUndefined();
    expect(body.thresholdCritical).toBe(200);
  });
});

describe("widget data derivation", () => {
  it("filters by service and region and builds line buckets", () => {
    const filtered = filterWidgetPoints(points, { ...widget, service: "api", region: "us", timeRange: "all" });
    expect(filtered).toHaveLength(2);
    expect(buildWidgetLine(filtered, widget)).toHaveLength(2);
  });
});

describe("query cache", () => {
  it("creates stable keys and deduplicates in-flight requests", async () => {
    const key = buildMetricQueryKey({ metric: "latency", aggregation: "avg", bucket: "1m", timeRange: "15m", sourceVersion: 1 });
    expect(key).toBe(buildMetricQueryKey({ metric: "latency", aggregation: "avg", bucket: "1m", timeRange: "15m", sourceVersion: 1 }));
    expect(key).not.toBe(buildMetricQueryKey({ workspaceId: "workspace-2", metric: "latency", aggregation: "avg", bucket: "1m", timeRange: "15m", sourceVersion: 1 }));
    const cache = new QueryCache<number>(1000);
    let calls = 0;
    const first = cache.get(key, async () => {
      calls += 1;
      return 42;
    });
    const second = cache.get(key, async () => 7);
    await expect(Promise.all([first, second])).resolves.toEqual([42, 42]);
    expect(calls).toBe(1);
  });
});
