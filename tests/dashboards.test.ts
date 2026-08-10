import { describe, expect, it, vi } from "vitest";
import { mapApiDashboard, widgetToApiBody } from "@/lib/api/dashboards";
import { buildMetricQueryKey, QueryCache } from "@/lib/dashboards/queryCache";
import { evaluateThreshold } from "@/lib/dashboards/thresholds";
import { buildWidgetLine, filterWidgetPoints } from "@/lib/dashboards/widgetData";
import { buildWidgetQueryKey, buildWidgetQueryRequest, effectiveHistoricalBucket, isHistoricalWidgetQuery, queryResponseToAggregatedPoints, theoreticalBucketCount } from "@/lib/query/mapping";
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
    const key = buildMetricQueryKey({ metric: "latency", aggregation: "avg", bucket: "1m", timeRange: "15m", start: 0, end: 60_000 });
    expect(key).toBe(buildMetricQueryKey({ metric: "latency", aggregation: "avg", bucket: "1m", timeRange: "15m", start: 0, end: 60_000 }));
    expect(key).not.toBe(buildMetricQueryKey({ workspaceId: "workspace-2", metric: "latency", aggregation: "avg", bucket: "1m", timeRange: "15m", start: 0, end: 60_000 }));
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

  it("keeps shared requests alive for consumers and aborts only on global clear", async () => {
    const cache = new QueryCache<number>(1000);
    let aborted = false;
    let resolve!: (value: number) => void;
    const first = cache.get("shared", (signal) => {
      signal.addEventListener("abort", () => { aborted = true; });
      return new Promise<number>((done) => { resolve = done; });
    });
    const second = cache.get("shared", async () => 7);
    resolve(42);
    await expect(Promise.all([first, second])).resolves.toEqual([42, 42]);
    expect(aborted).toBe(false);

    void cache.get("abort", (signal) => {
      signal.addEventListener("abort", () => { aborted = true; });
      return new Promise<number>(() => undefined);
    });
    cache.clear();
    expect(aborted).toBe(true);
  });

  it("expires successful entries and removes failed entries for retry", async () => {
    vi.useFakeTimers();
    try {
      const cache = new QueryCache<number>(1000);
      let calls = 0;
      await expect(cache.get("ok", async () => {
        calls += 1;
        return calls;
      })).resolves.toBe(1);
      await expect(cache.get("ok", async () => 99)).resolves.toBe(1);
      vi.advanceTimersByTime(1001);
      await expect(cache.get("ok", async () => {
        calls += 1;
        return calls;
      })).resolves.toBe(2);

      let failures = 0;
      await expect(cache.get("fail", async () => {
        failures += 1;
        throw new Error("boom");
      })).rejects.toThrow("boom");
      await expect(cache.get("fail", async () => {
        failures += 1;
        return 5;
      })).resolves.toBe(5);
      expect(failures).toBe(2);
    } finally {
      vi.useRealTimers();
    }
  });
});

describe("historical query mapping", () => {
  it("routes only remote historical line widgets to the Query Engine", () => {
    expect(isHistoricalWidgetQuery({ ...widget, timeRange: "1h" }, "remote", 3_600_000)).toBe(true);
    expect(isHistoricalWidgetQuery({ ...widget, timeRange: "15m" }, "remote", 3_600_000)).toBe(false);
    expect(isHistoricalWidgetQuery({ ...widget, timeRange: "1h" }, "simulation", 3_600_000)).toBe(false);
    expect(isHistoricalWidgetQuery({ ...widget, type: "scatter", timeRange: "1h" }, "remote", 3_600_000)).toBe(false);
  });

  it("maps widgets to Query Engine requests with explicit metric names and bounded ranges", () => {
    const mapped = buildWidgetQueryRequest({ ...widget, metric: "errorRate", aggregation: "avg", bucket: "1m", timeRange: "1h", service: "api", region: "us" }, 3_690_123);
    expect(mapped.request.metric).toBe("error_rate");
    expect(mapped.request.aggregation).toBe("avg");
    expect(mapped.request.bucket).toBe("1m");
    expect(mapped.request.filters).toEqual({ service: "api", region: "us" });
    expect(mapped.end).toBe(3_660_000);
    expect(mapped.start).toBe(60_000);
    expect(buildWidgetQueryKey({ workspaceId: "a", ...widget, start: mapped.start, end: mapped.end })).not.toBe(buildWidgetQueryKey({ workspaceId: "b", ...widget, start: mapped.start, end: mapped.end }));
  });

  it("coarsens all-range buckets before they exceed backend point limits", () => {
    const start = 0;
    const thirtyOneDays = 31 * 24 * 60 * 60 * 1000;
    expect(theoreticalBucketCount(start, thirtyOneDays, "10s")).toBe(267_840);
    expect(theoreticalBucketCount(start, thirtyOneDays, "1m")).toBe(44_640);
    expect(theoreticalBucketCount(start, thirtyOneDays, "5m")).toBe(8_928);
    expect(theoreticalBucketCount(start, thirtyOneDays, "15m")).toBe(2_976);
    expect(theoreticalBucketCount(start, thirtyOneDays, "1h")).toBe(744);
    expect(effectiveHistoricalBucket("1m", start, thirtyOneDays)).toBe("5m");
    expect(effectiveHistoricalBucket("5m", start, thirtyOneDays)).toBe("5m");
    expect(effectiveHistoricalBucket("1h", start, thirtyOneDays)).toBe("1h");

    const mapped = buildWidgetQueryRequest({ ...widget, bucket: "1m", timeRange: "all" }, thirtyOneDays + 123_456);
    expect(mapped.configuredBucket).toBe("1m");
    expect(mapped.effectiveBucket).toBe("5m");
    expect(mapped.request.bucket).toBe("5m");
    expect(mapped.request.start).toBe(new Date(mapped.start).toISOString());
    expect(mapped.request.end).toBe(new Date(mapped.end).toISOString());
  });

  it("transforms query series without converting nulls to zero", () => {
    const points = queryResponseToAggregatedPoints({
      metric: "latency",
      unit: "ms",
      aggregation: "avg",
      bucket: "1m",
      groupBy: null,
      filters: {},
      series: [{ group: null, points: [
        { timestamp: "2026-08-10T00:02:00.000Z", value: 175, count: 1 },
        { timestamp: "2026-08-10T00:00:00.000Z", value: null, count: 0 },
        { timestamp: "2026-08-10T00:01:00.000Z", value: 125, count: 2 },
        { timestamp: "invalid", value: 200, count: 1 },
      ] }],
      metadata: { start: "2026-08-10T00:00:00.000Z", end: "2026-08-10T00:02:00.000Z", executionTimeMs: 1, returnedPoints: 2, maxPoints: 10000, maxGroups: 100, limited: true, truncatedReason: "max_points" },
    });
    expect(points).toEqual([
      { timestamp: Date.parse("2026-08-10T00:01:00.000Z"), avg: 125, min: 125, max: 125, count: 2 },
      { timestamp: Date.parse("2026-08-10T00:02:00.000Z"), avg: 175, min: 175, max: 175, count: 1 },
    ]);
  });
});
