"use client";

import { memo, useEffect, useMemo, useState } from "react";
import { BarChart } from "@/components/charts/BarChart";
import { Heatmap } from "@/components/charts/Heatmap";
import { LineChart } from "@/components/charts/LineChart";
import { ScatterPlot } from "@/components/charts/ScatterPlot";
import { useDashboardConfig } from "@/hooks/useDashboardConfig";
import { useTelemetryQuery } from "@/hooks/useTelemetryQuery";
import { useDashboardControls } from "@/hooks/useDashboardControls";
import { useAuth } from "@/components/providers/AuthProvider";
import { ObservaApiClient } from "@/lib/api/client";
import { getObservaApiUrl } from "@/lib/api/config";
import { QueryCache } from "@/lib/dashboards/queryCache";
import { evaluateThreshold } from "@/lib/dashboards/thresholds";
import { buildWidgetHeatmap, buildWidgetLine, filterWidgetPoints, summarizeWidget } from "@/lib/dashboards/widgetData";
import { QueryEngineApi } from "@/lib/query/client";
import { buildWidgetQueryKey, buildWidgetQueryRequest, extractScalarValue, isHistoricalBarQuery, isHistoricalLineQuery, isHistoricalStatQuery, queryResponseToAggregatedPoints, queryResponseToBars } from "@/lib/query/mapping";
import type { DashboardWidgetConfig, MetricBucket, ThresholdState, WidgetAggregation, WidgetType } from "@/lib/dashboards/types";
import type { AggregatedPoint, MetricName } from "@/lib/types";
import type { TelemetryQueryResult } from "@/hooks/useTelemetryQuery";
import type { ReactNode } from "react";

const widgetTypes: WidgetType[] = ["line", "bar", "scatter", "heatmap", "stat"];
const metrics: MetricName[] = ["latency", "throughput", "cpuUsage", "memoryUsage", "errorRate", "payloadSize"];
const aggregations: WidgetAggregation[] = ["avg", "min", "max", "sum", "count"];
const buckets: MetricBucket[] = ["raw", "1m", "5m", "1h"];
const ranges: DashboardWidgetConfig["timeRange"][] = ["5m", "15m", "1h", "6h", "all"];
const backendWidgetCache = new QueryCache<unknown>(10_000, 64);

interface RendererProps {
  widget: DashboardWidgetConfig;
  telemetry: TelemetryQueryResult;
}

function thresholdClass(state: ThresholdState): string {
  if (state === "critical") return "threshold-critical";
  if (state === "warning") return "threshold-warning";
  return "threshold-normal";
}

function useHistoricalStat(widget: DashboardWidgetConfig, telemetry: TelemetryQueryResult): { value: number | null; state: ThresholdState; limited: boolean; error: string | null } | null {
  const { sourceKind } = useDashboardControls();
  const { activeWorkspace } = useAuth();
  const latestTimestamp = telemetry.latestTimestamp;
  const shouldUseHistorical = isHistoricalStatQuery(widget, sourceKind, latestTimestamp);
  const queryWindow = useMemo(() => shouldUseHistorical && latestTimestamp !== null ? buildWidgetQueryRequest(widget, latestTimestamp, { bucket: "raw" }) : null, [latestTimestamp, shouldUseHistorical, widget]);
  const queryKey = useMemo(() => buildWidgetQueryKey({
    metric: widget.metric,
    workspaceId: activeWorkspace?.id,
    aggregation: widget.aggregation,
    bucket: "raw",
    service: widget.service,
    region: widget.region,
    timeRange: widget.timeRange,
    start: queryWindow?.start,
    end: queryWindow?.end,
  }), [activeWorkspace?.id, queryWindow?.end, queryWindow?.start, widget]);
  const requestBody = useMemo(() => queryWindow ? JSON.stringify(queryWindow.request) : "", [queryWindow]);
  const [result, setResult] = useState<{ key: string; value: number | null; state: ThresholdState; limited: boolean; error: string | null } | null>(null);
  useEffect(() => {
    if (!shouldUseHistorical || !requestBody) return undefined;
    let active = true;
    const api = new QueryEngineApi(new ObservaApiClient({ baseUrl: getObservaApiUrl() }));
    void backendWidgetCache.get(queryKey, (signal) => api.run(JSON.parse(requestBody), signal).then((response) => ({
      value: extractScalarValue(response),
      limited: response.metadata.limited,
    }))).then((payload) => {
      const typed = payload as { value: number | null; limited: boolean };
      if (active) setResult({ key: queryKey, value: typed.value, state: typed.value === null ? "normal" : evaluateThreshold(typed.value, widget), limited: typed.limited, error: null });
    }).catch((error: unknown) => {
      if (active && !(error instanceof DOMException && error.name === "AbortError")) {
        setResult({ key: queryKey, value: null, state: "normal", limited: false, error: error instanceof Error ? error.message : "Historical query failed" });
      }
    });
    return () => {
      active = false;
    };
  }, [queryKey, requestBody, shouldUseHistorical, widget]);
  if (!shouldUseHistorical) return null;
  return result?.key === queryKey ? result : { value: null, state: "normal", limited: false, error: null };
}

function StatWidget({ widget, telemetry }: RendererProps) {
  const filtered = useMemo(() => filterWidgetPoints(telemetry.allPoints, widget), [telemetry.allPoints, widget]);
  const summary = useMemo(() => summarizeWidget(filtered, widget), [filtered, widget]);
  const historical = useHistoricalStat(widget, telemetry);
  const display = historical ?? summary;
  return (
    <div className={`widget-stat ${thresholdClass(display.state)}`}>
      <span>{widget.metric}</span>
      <strong>{display.value === null ? "--" : display.value.toFixed(widget.metric === "errorRate" ? 2 : 1)}</strong>
      <small>{display.state}</small>
      {historical?.limited ? <span className="query-note">Result limited</span> : null}
      {historical?.error ? <span className="form-error">Historical query unavailable</span> : null}
    </div>
  );
}

function useLinePoints(widget: DashboardWidgetConfig, telemetry: TelemetryQueryResult): { points: AggregatedPoint[]; limited: boolean; error: string | null; effectiveBucket: string | null } {
  const { sourceKind } = useDashboardControls();
  const { activeWorkspace } = useAuth();
  const filtered = useMemo(() => filterWidgetPoints(telemetry.allPoints, widget), [telemetry.allPoints, widget]);
  const [backendResult, setBackendResult] = useState<{ key: string; points: AggregatedPoint[]; limited: boolean; error: string | null; effectiveBucket: string | null } | null>(null);
  const latestTimestamp = telemetry.latestTimestamp;
  const shouldUseHistorical = isHistoricalLineQuery(widget, sourceKind, latestTimestamp);
  const queryWindow = useMemo(() => shouldUseHistorical && latestTimestamp !== null ? buildWidgetQueryRequest(widget, latestTimestamp) : null, [latestTimestamp, shouldUseHistorical, widget]);
  const queryKey = useMemo(() => buildWidgetQueryKey({
    metric: widget.metric,
    workspaceId: activeWorkspace?.id,
    aggregation: widget.aggregation,
    bucket: widget.bucket,
    groupBy: undefined,
    service: widget.service,
    region: widget.region,
    timeRange: widget.timeRange,
    start: queryWindow?.start,
    end: queryWindow?.end,
  }), [activeWorkspace?.id, queryWindow?.end, queryWindow?.start, widget]);
  const requestBody = useMemo(() => queryWindow ? JSON.stringify(queryWindow.request) : "", [queryWindow]);
  const effectiveBucket = queryWindow?.effectiveBucket ?? null;
  useEffect(() => {
    if (!shouldUseHistorical || !requestBody) return undefined;
    let active = true;
    const api = new QueryEngineApi(new ObservaApiClient({ baseUrl: getObservaApiUrl() }));
    void backendWidgetCache.get(queryKey, (signal) => api.run(JSON.parse(requestBody), signal).then((response) => ({
      points: queryResponseToAggregatedPoints(response),
      limited: response.metadata.limited,
    }))).then((payload) => {
      const result = payload as { points: AggregatedPoint[]; limited: boolean };
      if (active) setBackendResult({ key: queryKey, points: result.points, limited: result.limited, error: null, effectiveBucket });
    }).catch((error: unknown) => {
      if (active && !(error instanceof DOMException && error.name === "AbortError")) {
        setBackendResult({ key: queryKey, points: [], limited: false, error: error instanceof Error ? error.message : "Historical query failed", effectiveBucket });
      }
    });
    return () => {
      active = false;
    };
  }, [effectiveBucket, queryKey, requestBody, shouldUseHistorical]);
  if (shouldUseHistorical && backendResult?.key === queryKey) {
    return { points: backendResult.error ? buildWidgetLine(filtered, widget) : backendResult.points, limited: backendResult.limited, error: backendResult.error, effectiveBucket: backendResult.effectiveBucket };
  }
  return { points: buildWidgetLine(filtered, widget), limited: false, error: null, effectiveBucket: null };
}

function useBarData(widget: DashboardWidgetConfig, telemetry: TelemetryQueryResult): { bars: Array<{ service: string; throughput: number; count: number }> | null; limited: boolean; error: string | null } {
  const { sourceKind } = useDashboardControls();
  const { activeWorkspace } = useAuth();
  const latestTimestamp = telemetry.latestTimestamp;
  const shouldUseHistorical = isHistoricalBarQuery(widget, sourceKind, latestTimestamp);
  const queryWindow = useMemo(() => shouldUseHistorical && latestTimestamp !== null ? buildWidgetQueryRequest(widget, latestTimestamp, { bucket: "raw", groupBy: "service" }) : null, [latestTimestamp, shouldUseHistorical, widget]);
  const queryKey = useMemo(() => buildWidgetQueryKey({
    metric: widget.metric,
    workspaceId: activeWorkspace?.id,
    aggregation: widget.aggregation,
    bucket: "raw",
    groupBy: "service",
    service: widget.service,
    region: widget.region,
    timeRange: widget.timeRange,
    start: queryWindow?.start,
    end: queryWindow?.end,
  }), [activeWorkspace?.id, queryWindow?.end, queryWindow?.start, widget]);
  const requestBody = useMemo(() => queryWindow ? JSON.stringify(queryWindow.request) : "", [queryWindow]);
  const [backendResult, setBackendResult] = useState<{ key: string; bars: Array<{ service: string; throughput: number; count: number }>; limited: boolean; error: string | null } | null>(null);
  useEffect(() => {
    if (!shouldUseHistorical || !requestBody) return undefined;
    let active = true;
    const api = new QueryEngineApi(new ObservaApiClient({ baseUrl: getObservaApiUrl() }));
    void backendWidgetCache.get(queryKey, (signal) => api.run(JSON.parse(requestBody), signal).then((response) => ({
      bars: queryResponseToBars(response),
      limited: response.metadata.limited,
    }))).then((payload) => {
      const result = payload as { bars: Array<{ service: string; throughput: number; count: number }>; limited: boolean };
      if (active) setBackendResult({ key: queryKey, bars: result.bars, limited: result.limited, error: null });
    }).catch((error: unknown) => {
      if (active && !(error instanceof DOMException && error.name === "AbortError")) {
        setBackendResult({ key: queryKey, bars: [], limited: false, error: error instanceof Error ? error.message : "Historical query failed" });
      }
    });
    return () => {
      active = false;
    };
  }, [queryKey, requestBody, shouldUseHistorical]);
  if (shouldUseHistorical && backendResult?.key === queryKey) return { bars: backendResult.error ? null : backendResult.bars, limited: backendResult.limited, error: backendResult.error };
  return { bars: null, limited: false, error: null };
}

function BarWidget({ widget, telemetry }: RendererProps) {
  const result = useBarData(widget, telemetry);
  return (
    <>
      {result.bars ? <BarChart data={result.bars} /> : <BarChart points={filterWidgetPoints(telemetry.allPoints, widget)} />}
      {result.limited ? <span className="query-note">Result limited</span> : null}
      {result.error ? <span className="form-error">Historical query unavailable</span> : null}
    </>
  );
}

function LineWidget(props: RendererProps) {
  const result = useLinePoints(props.widget, props.telemetry);
  return (
    <>
      <LineChart points={result.points} />
      {result.limited ? <span className="query-note">Result limited</span> : null}
      {result.effectiveBucket && result.effectiveBucket !== props.widget.bucket ? <span className="query-note">Using {result.effectiveBucket} resolution</span> : null}
      {result.error ? <span className="form-error">Historical query unavailable</span> : null}
    </>
  );
}

function WidgetEditForm({ widget, onCancel }: { widget: DashboardWidgetConfig; onCancel: () => void }) {
  const { activeDashboard, updateWidget } = useDashboardConfig();
  const { availableServices } = useDashboardControls();
  const [draft, setDraft] = useState(widget);
  const [message, setMessage] = useState<string | null>(null);
  const numberValue = (value: number | undefined) => value === undefined ? "" : String(value);
  const parseNumber = (value: string) => value.trim() === "" ? undefined : Number(value);
  const save = async () => {
    if (!draft.title.trim()) {
      setMessage("Title is required");
      return;
    }
    if (
      (draft.thresholdWarning !== undefined && !Number.isFinite(draft.thresholdWarning)) ||
      (draft.thresholdCritical !== undefined && !Number.isFinite(draft.thresholdCritical))
    ) {
      setMessage("Thresholds must be finite numbers");
      return;
    }
    if (
      draft.thresholdWarning !== undefined &&
      draft.thresholdCritical !== undefined &&
      draft.thresholdWarning > draft.thresholdCritical
    ) {
      setMessage("Warning must be less than or equal to critical");
      return;
    }
    await updateWidget({ ...draft, title: draft.title.trim() });
    onCancel();
  };
  return (
    <div className="widget-edit-form">
      <label>Title<input aria-label={`Edit title for ${widget.title}`} value={draft.title} onChange={(event) => setDraft((current) => ({ ...current, title: event.target.value }))} /></label>
      <label>Type<select aria-label={`Edit type for ${widget.title}`} value={draft.type} onChange={(event) => setDraft((current) => ({ ...current, type: event.target.value as WidgetType }))}>{widgetTypes.map((item) => <option key={item} value={item}>{item}</option>)}</select></label>
      <label>Metric<select aria-label={`Edit metric for ${widget.title}`} value={draft.metric} onChange={(event) => setDraft((current) => ({ ...current, metric: event.target.value as MetricName }))}>{metrics.map((item) => <option key={item} value={item}>{item}</option>)}</select></label>
      <label>Aggregation<select aria-label={`Edit aggregation for ${widget.title}`} value={draft.aggregation} onChange={(event) => setDraft((current) => ({ ...current, aggregation: event.target.value as WidgetAggregation }))}>{aggregations.map((item) => <option key={item} value={item}>{item}</option>)}</select></label>
      <label>Bucket<select aria-label={`Edit bucket for ${widget.title}`} value={draft.bucket} onChange={(event) => setDraft((current) => ({ ...current, bucket: event.target.value as MetricBucket }))}>{buckets.map((item) => <option key={item} value={item}>{item}</option>)}</select></label>
      <label>Time range<select aria-label={`Edit time range for ${widget.title}`} value={draft.timeRange} onChange={(event) => setDraft((current) => ({ ...current, timeRange: event.target.value as DashboardWidgetConfig["timeRange"] }))}>{ranges.map((item) => <option key={item} value={item}>{item}</option>)}</select></label>
      <label>Service<input aria-label={`Edit service for ${widget.title}`} list="widget-services" value={draft.service ?? ""} onChange={(event) => setDraft((current) => ({ ...current, service: event.target.value || undefined }))} /></label>
      <label>Region<input aria-label={`Edit region for ${widget.title}`} value={draft.region ?? ""} onChange={(event) => setDraft((current) => ({ ...current, region: event.target.value || undefined }))} /></label>
      <label>Warning<input aria-label={`Edit warning threshold for ${widget.title}`} type="number" value={numberValue(draft.thresholdWarning)} onChange={(event) => setDraft((current) => ({ ...current, thresholdWarning: parseNumber(event.target.value) }))} /></label>
      <label>Critical<input aria-label={`Edit critical threshold for ${widget.title}`} type="number" value={numberValue(draft.thresholdCritical)} onChange={(event) => setDraft((current) => ({ ...current, thresholdCritical: parseNumber(event.target.value) }))} /></label>
      <datalist id="widget-services">{availableServices.map((service) => <option key={service} value={service} />)}</datalist>
      <div className="widget-edit-actions">
        <button type="button" onClick={() => void save()} disabled={activeDashboard.system}>Save</button>
        <button type="button" onClick={onCancel}>Cancel</button>
      </div>
      {message ? <span className="form-error">{message}</span> : null}
    </div>
  );
}

const renderers = {
  line: (props: RendererProps) => <LineWidget {...props} />,
  bar: (props: RendererProps) => <BarWidget {...props} />,
  scatter: ({ widget, telemetry }: RendererProps) => <ScatterPlot points={filterWidgetPoints(telemetry.allPoints, widget)} />,
  heatmap: ({ widget, telemetry }: RendererProps) => <Heatmap cells={buildWidgetHeatmap(filterWidgetPoints(telemetry.allPoints, widget))} />,
  stat: (props: RendererProps) => <StatWidget {...props} />,
} satisfies Record<DashboardWidgetConfig["type"], (props: RendererProps) => ReactNode>;

export const DashboardWidgetRenderer = memo(function DashboardWidgetRenderer({ widget, telemetry }: RendererProps) {
  const { activeDashboard, moveWidget, removeWidget } = useDashboardConfig();
  const [editing, setEditing] = useState(false);
  const summary = useMemo(() => summarizeWidget(filterWidgetPoints(telemetry.allPoints, widget), widget), [telemetry.allPoints, widget]);
  return (
    <article className={`panel chart-card ${widget.width === 2 ? "wide" : ""} widget-card ${thresholdClass(summary.state)}`}>
      <div className="widget-heading">
        <h2>{widget.title}</h2>
        <span>{widget.metric} / {widget.timeRange}</span>
        {!activeDashboard.system ? (
          <div className="widget-actions">
            <button type="button" aria-label={`Edit ${widget.title}`} onClick={() => setEditing((current) => !current)}>{editing ? "Close" : "Edit"}</button>
            <button type="button" aria-label={`Move ${widget.title} up`} onClick={() => void moveWidget(widget.id, -1)}>Up</button>
            <button type="button" aria-label={`Move ${widget.title} down`} onClick={() => void moveWidget(widget.id, 1)}>Down</button>
            <button type="button" className="danger" aria-label={`Remove ${widget.title}`} onClick={() => void removeWidget(widget.id)}>Remove</button>
          </div>
        ) : null}
      </div>
      {editing ? <WidgetEditForm widget={widget} onCancel={() => setEditing(false)} /> : null}
      {renderers[widget.type]({ widget, telemetry })}
      {summary.state !== "normal" ? <div className="threshold-badge">{summary.state}</div> : null}
    </article>
  );
});

export function DashboardWidgetGrid() {
  const { activeDashboard } = useDashboardConfig();
  const { activeWorkspace } = useAuth();
  const telemetry = useTelemetryQuery();
  const widgets = [...activeDashboard.widgets].sort((a, b) => a.position - b.position || a.id.localeCompare(b.id));
  useEffect(() => {
    backendWidgetCache.clear();
  }, [activeDashboard.id, activeWorkspace?.id]);
  if (widgets.length === 0) {
    return <section className="panel empty-state"><h2>No widgets yet</h2><p>Add a widget to start building this dashboard.</p></section>;
  }
  return (
    <section className="charts-grid">
      {widgets.map((widget) => <DashboardWidgetRenderer key={widget.id} widget={widget} telemetry={telemetry} />)}
    </section>
  );
}
