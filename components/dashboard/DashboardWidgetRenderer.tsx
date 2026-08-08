"use client";

import { memo, useEffect, useMemo, useState } from "react";
import { BarChart } from "@/components/charts/BarChart";
import { Heatmap } from "@/components/charts/Heatmap";
import { LineChart } from "@/components/charts/LineChart";
import { ScatterPlot } from "@/components/charts/ScatterPlot";
import { useDashboardConfig } from "@/hooks/useDashboardConfig";
import { useTelemetryQuery } from "@/hooks/useTelemetryQuery";
import { useDashboardControls } from "@/hooks/useDashboardControls";
import { TelemetryApi, rangeToStart } from "@/lib/api/telemetry";
import { ObservaApiClient } from "@/lib/api/client";
import { getObservaApiUrl } from "@/lib/api/config";
import { buildMetricQueryKey, QueryCache } from "@/lib/dashboards/queryCache";
import { buildWidgetHeatmap, buildWidgetLine, filterWidgetPoints, summarizeWidget } from "@/lib/dashboards/widgetData";
import type { DashboardWidgetConfig, MetricBucket, ThresholdState, WidgetAggregation, WidgetType } from "@/lib/dashboards/types";
import type { AggregatedPoint, MetricName } from "@/lib/types";
import type { TelemetryQueryResult } from "@/hooks/useTelemetryQuery";
import type { ReactNode } from "react";

const widgetTypes: WidgetType[] = ["line", "bar", "scatter", "heatmap", "stat"];
const metrics: MetricName[] = ["latency", "throughput", "cpuUsage", "memoryUsage", "errorRate", "payloadSize"];
const aggregations: WidgetAggregation[] = ["avg", "min", "max", "sum", "count"];
const buckets: MetricBucket[] = ["raw", "1m", "5m", "1h"];
const ranges: DashboardWidgetConfig["timeRange"][] = ["5m", "15m", "1h", "6h", "all"];
const backendLineCache = new QueryCache<AggregatedPoint[]>(10_000, 32);

interface RendererProps {
  widget: DashboardWidgetConfig;
  telemetry: TelemetryQueryResult;
}

function thresholdClass(state: ThresholdState): string {
  if (state === "critical") return "threshold-critical";
  if (state === "warning") return "threshold-warning";
  return "threshold-normal";
}

function StatWidget({ widget, telemetry }: RendererProps) {
  const filtered = useMemo(() => filterWidgetPoints(telemetry.allPoints, widget), [telemetry.allPoints, widget]);
  const summary = useMemo(() => summarizeWidget(filtered, widget), [filtered, widget]);
  return (
    <div className={`widget-stat ${thresholdClass(summary.state)}`}>
      <span>{widget.metric}</span>
      <strong>{summary.value === null ? "--" : summary.value.toFixed(widget.metric === "errorRate" ? 2 : 1)}</strong>
      <small>{summary.state}</small>
    </div>
  );
}

function shouldUseBackendLine(widget: DashboardWidgetConfig, latestTimestamp: number | null, sourceKind: string): boolean {
  return sourceKind === "remote" && widget.type === "line" && widget.bucket !== "raw" && (widget.timeRange === "1h" || widget.timeRange === "6h" || widget.timeRange === "all") && latestTimestamp !== null;
}

function useLinePoints(widget: DashboardWidgetConfig, telemetry: TelemetryQueryResult): AggregatedPoint[] {
  const { sourceKind } = useDashboardControls();
  const filtered = useMemo(() => filterWidgetPoints(telemetry.allPoints, widget), [telemetry.allPoints, widget]);
  const [backendResult, setBackendResult] = useState<{ key: string; points: AggregatedPoint[] } | null>(null);
  const latestTimestamp = telemetry.latestTimestamp;
  const latestMinute = latestTimestamp === null ? 0 : Math.floor(latestTimestamp / 60_000);
  const queryKey = useMemo(() => buildMetricQueryKey({
    metric: widget.metric,
    aggregation: widget.aggregation,
    bucket: widget.bucket,
    service: widget.service,
    region: widget.region,
    timeRange: widget.timeRange,
    sourceVersion: latestMinute,
  }), [latestMinute, widget]);
  useEffect(() => {
    if (!shouldUseBackendLine(widget, latestTimestamp, sourceKind)) return undefined;
    let active = true;
    const api = new TelemetryApi(new ObservaApiClient({ baseUrl: getObservaApiUrl() }));
    const start = latestTimestamp === null ? undefined : rangeToStart(widget.timeRange, latestTimestamp);
    void backendLineCache.get(queryKey, (signal) => api.queryMetric({
      signal,
      metric: widget.metric,
      aggregation: widget.aggregation === "raw" ? "avg" : widget.aggregation,
      bucket: widget.bucket,
      service: widget.service ?? "all",
      region: widget.region,
      start,
      end: latestTimestamp ?? undefined,
    }).then((response) => response.points.map((point) => ({
      timestamp: Date.parse(point.timestamp),
      avg: point.value,
      min: point.value,
      max: point.value,
      count: point.count,
    })))).then((points) => {
      if (active) setBackendResult({ key: queryKey, points });
    }).catch(() => undefined);
    return () => {
      active = false;
    };
  }, [latestTimestamp, queryKey, sourceKind, widget]);
  return shouldUseBackendLine(widget, latestTimestamp, sourceKind) && backendResult?.key === queryKey ? backendResult.points : buildWidgetLine(filtered, widget);
}

function LineWidget(props: RendererProps) {
  return <LineChart points={useLinePoints(props.widget, props.telemetry)} />;
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
  bar: ({ widget, telemetry }: RendererProps) => <BarChart points={filterWidgetPoints(telemetry.allPoints, widget)} />,
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
  const telemetry = useTelemetryQuery();
  const widgets = [...activeDashboard.widgets].sort((a, b) => a.position - b.position || a.id.localeCompare(b.id));
  if (widgets.length === 0) {
    return <section className="panel empty-state"><h2>No widgets yet</h2><p>Add a widget to start building this dashboard.</p></section>;
  }
  return (
    <section className="charts-grid">
      {widgets.map((widget) => <DashboardWidgetRenderer key={widget.id} widget={widget} telemetry={telemetry} />)}
    </section>
  );
}
