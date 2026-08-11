"use client";

import { useMemo, useState } from "react";
import { useDashboardConfig } from "@/hooks/useDashboardConfig";
import { useAuth } from "@/components/providers/AuthProvider";
import type { MetricName } from "@/lib/types";
import type { WidgetDraft, WidgetType } from "@/lib/dashboards/types";

const widgetTypes: WidgetType[] = ["line", "bar", "scatter", "heatmap", "stat"];
const metrics: MetricName[] = ["latency", "throughput", "cpuUsage", "memoryUsage", "errorRate", "payloadSize"];

export function DashboardSelector() {
  const config = useDashboardConfig();
  const auth = useAuth();
  const [name, setName] = useState("");
  const [rename, setRename] = useState("");
  const [draft, setDraft] = useState<WidgetDraft>({ title: "New latency widget", type: "line", metric: "latency", aggregation: "avg", bucket: "1m", timeRange: "15m" });
  const active = config.activeDashboard;
  const canEdit = !active.system && auth.activeWorkspace?.role !== "viewer";
  const status = useMemo(() => {
    if (config.loading) return "Loading dashboards...";
    if (config.error) return "Saved dashboards unavailable";
    return `${config.dashboards.length - 1} saved`;
  }, [config.dashboards.length, config.error, config.loading]);

  return (
    <section className="panel dashboard-config-panel">
      <div className="section-heading">
        <h2>Dashboards</h2>
        <span>{status}</span>
      </div>
      <div className="dashboard-config-grid">
        <label>Active dashboard
          <select aria-label="Saved dashboard" value={active.id} onChange={(event) => config.selectDashboard(event.target.value)}>
            {config.dashboards.map((dashboard) => <option key={dashboard.id} value={dashboard.id}>{dashboard.name}</option>)}
          </select>
        </label>
        <label>Create
          <input aria-label="New dashboard name" value={name} onChange={(event) => setName(event.target.value)} placeholder="Dashboard name" />
        </label>
        <button type="button" onClick={() => { if (name.trim()) void config.createDashboard(name.trim()).then(() => setName("")); }}>Create</button>
        <label>Rename
          <input aria-label="Rename dashboard" value={rename} onChange={(event) => setRename(event.target.value)} placeholder={active.name} disabled={!canEdit} />
        </label>
        <button type="button" disabled={!canEdit} onClick={() => { if (rename.trim()) void config.renameDashboard(active.id, rename.trim()).then(() => setRename("")); }}>Rename</button>
        <button type="button" className="danger" disabled={!canEdit} onClick={() => { if (window.confirm(`Delete ${active.name}?`)) void config.deleteDashboard(active.id); }}>Delete</button>
      </div>
      <div className="widget-config-row">
        <label>Widget type
          <select aria-label="Widget type" value={draft.type} disabled={!canEdit} onChange={(event) => setDraft((current) => ({ ...current, type: event.target.value as WidgetType }))}>
            {widgetTypes.map((type) => <option key={type} value={type}>{type}</option>)}
          </select>
        </label>
        <label>Metric
          <select aria-label="Widget metric" value={draft.metric} disabled={!canEdit} onChange={(event) => setDraft((current) => ({ ...current, metric: event.target.value as MetricName }))}>
            {metrics.map((metric) => <option key={metric} value={metric}>{metric}</option>)}
          </select>
        </label>
        <label>Title
          <input aria-label="Widget title" value={draft.title} disabled={!canEdit} onChange={(event) => setDraft((current) => ({ ...current, title: event.target.value }))} />
        </label>
        <label>Warning
          <input aria-label="Warning threshold" type="number" disabled={!canEdit} onChange={(event) => setDraft((current) => ({ ...current, thresholdWarning: event.target.value ? Number(event.target.value) : undefined }))} />
        </label>
        <label>Critical
          <input aria-label="Critical threshold" type="number" disabled={!canEdit} onChange={(event) => setDraft((current) => ({ ...current, thresholdCritical: event.target.value ? Number(event.target.value) : undefined }))} />
        </label>
        <button type="button" disabled={!canEdit} onClick={() => void config.addWidget(draft)}>Add widget</button>
      </div>
    </section>
  );
}
