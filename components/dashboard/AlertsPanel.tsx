"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertsApi } from "@/lib/api/alerts";
import { validateAlertDraft } from "@/lib/alerts/validation";
import type { AlertAggregation, AlertBucket, AlertOperator, AlertRule, AlertRuleDraft, Incident } from "@/lib/alerts/types";
import type { MetricName, Region, ServiceId } from "@/lib/types";

const metrics: MetricName[] = ["latency", "throughput", "cpuUsage", "memoryUsage", "errorRate", "payloadSize"];
const operators: AlertOperator[] = [">", ">=", "<", "<="];
const aggregations: AlertAggregation[] = ["avg", "min", "max", "sum", "count"];
const buckets: AlertBucket[] = ["raw", "1m", "5m", "1h"];

const initialDraft: AlertRuleDraft = {
  name: "High latency",
  metric: "latency",
  operator: ">=",
  threshold: 200,
  aggregation: "avg",
  bucket: "raw",
  evaluationWindowSeconds: 300,
  evaluationIntervalSeconds: 60,
  cooldownSeconds: 300,
  enabled: true,
};

function formatDate(value?: string): string {
  return value ? new Date(value).toLocaleTimeString() : "--";
}

export function AlertsPanel() {
  const api = useMemo(() => new AlertsApi(), []);
  const [alerts, setAlerts] = useState<AlertRule[]>([]);
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [draft, setDraft] = useState<AlertRuleDraft>(initialDraft);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const latestRequestRef = useRef(0);
  const pollingInFlightRef = useRef(false);

  const reload = useCallback(async (signal?: AbortSignal, skipIfPending = false) => {
    if (skipIfPending && pollingInFlightRef.current) return;
    pollingInFlightRef.current = true;
    const requestId = latestRequestRef.current + 1;
    latestRequestRef.current = requestId;
    try {
      const [rules, history] = await Promise.all([api.listAlerts(signal), api.listIncidents(signal)]);
      if (signal?.aborted || requestId !== latestRequestRef.current) return;
      setAlerts(rules);
      setIncidents(history);
      setMessage(null);
    } catch (error) {
      if (signal?.aborted || requestId !== latestRequestRef.current) return;
      setMessage(error instanceof Error ? error.message : "Alerts unavailable");
    } finally {
      pollingInFlightRef.current = false;
    }
  }, [api]);

  useEffect(() => {
    const controller = new AbortController();
    const initial = window.setTimeout(() => void reload(controller.signal), 0);
    const timer = window.setInterval(() => void reload(controller.signal, true), 10_000);
    return () => {
      controller.abort();
      window.clearTimeout(initial);
      window.clearInterval(timer);
    };
  }, [reload]);

  const save = async () => {
    const validation = validateAlertDraft(draft);
    if (validation) {
      setMessage(validation);
      return;
    }
    try {
      if (editingId) await api.updateAlert(editingId, draft);
      else await api.createAlert(draft);
      setDraft(initialDraft);
      setEditingId(null);
      await reload();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Alert save failed");
    }
  };

  const edit = (rule: AlertRule) => {
    setEditingId(rule.id);
    setDraft({
      name: rule.name,
      metric: rule.metric,
      operator: rule.operator,
      threshold: rule.threshold,
      aggregation: rule.aggregation,
      bucket: rule.bucket,
      evaluationWindowSeconds: rule.evaluationWindowSeconds,
      evaluationIntervalSeconds: rule.evaluationIntervalSeconds,
      cooldownSeconds: rule.cooldownSeconds,
      service: rule.service,
      region: rule.region,
      enabled: rule.enabled,
    });
  };

  return (
    <section className="panel alerts-panel">
      <div className="section-heading"><h2>Alerts</h2><span>{message ?? `${alerts.length} rules / ${incidents.length} incidents`}</span></div>
      <div className="alert-form">
        <label>Name<input aria-label="Alert name" value={draft.name} onChange={(event) => setDraft((current) => ({ ...current, name: event.target.value }))} /></label>
        <label>Metric<select aria-label="Alert metric" value={draft.metric} onChange={(event) => setDraft((current) => ({ ...current, metric: event.target.value as MetricName }))}>{metrics.map((metric) => <option key={metric} value={metric}>{metric}</option>)}</select></label>
        <label>Operator<select aria-label="Alert operator" value={draft.operator} onChange={(event) => setDraft((current) => ({ ...current, operator: event.target.value as AlertOperator }))}>{operators.map((op) => <option key={op} value={op}>{op}</option>)}</select></label>
        <label>Threshold<input aria-label="Alert threshold" type="number" value={draft.threshold} onChange={(event) => setDraft((current) => ({ ...current, threshold: Number(event.target.value) }))} /></label>
        <label>Aggregation<select aria-label="Alert aggregation" value={draft.aggregation} onChange={(event) => setDraft((current) => ({ ...current, aggregation: event.target.value as AlertAggregation }))}>{aggregations.map((item) => <option key={item} value={item}>{item}</option>)}</select></label>
        <label>Bucket<select aria-label="Alert bucket" value={draft.bucket} onChange={(event) => setDraft((current) => ({ ...current, bucket: event.target.value as AlertBucket }))}>{buckets.map((item) => <option key={item} value={item}>{item}</option>)}</select></label>
        <label>Service<input aria-label="Alert service filter" placeholder="Any service" value={draft.service ?? ""} onChange={(event) => setDraft((current) => ({ ...current, service: event.target.value.trim() ? event.target.value.trim() as ServiceId : undefined }))} /></label>
        <label>Region<input aria-label="Alert region filter" placeholder="Any region" value={draft.region ?? ""} onChange={(event) => setDraft((current) => ({ ...current, region: event.target.value.trim() ? event.target.value.trim() as Region : undefined }))} /></label>
        <label>Window<input aria-label="Alert evaluation window" type="number" value={draft.evaluationWindowSeconds} onChange={(event) => setDraft((current) => ({ ...current, evaluationWindowSeconds: Number(event.target.value) }))} /></label>
        <label>Interval<input aria-label="Alert evaluation interval" type="number" value={draft.evaluationIntervalSeconds} onChange={(event) => setDraft((current) => ({ ...current, evaluationIntervalSeconds: Number(event.target.value) }))} /></label>
        <label>Cooldown<input aria-label="Alert cooldown" type="number" value={draft.cooldownSeconds} onChange={(event) => setDraft((current) => ({ ...current, cooldownSeconds: Number(event.target.value) }))} /></label>
        <button type="button" onClick={() => void save()}>{editingId ? "Save alert" : "Create alert"}</button>
      </div>
      <div className="alerts-grid">
        <div className="alert-list">
          {alerts.length === 0 ? <p>No alert rules yet.</p> : alerts.map((rule) => (
            <article className={`alert-row ${rule.state}`} key={rule.id}>
              <strong>{rule.name}</strong>
              <span>{rule.metric} {rule.operator} {rule.threshold} / {rule.state}</span>
              <span>Evaluated {formatDate(rule.lastEvaluatedAt)}</span>
              <div>
                <button type="button" onClick={() => edit(rule)}>Edit</button>
                <button type="button" onClick={() => void api.updateAlert(rule.id, { enabled: !rule.enabled }).then(() => reload()).catch((error: unknown) => setMessage(error instanceof Error ? error.message : "Alert update failed"))}>{rule.enabled ? "Disable" : "Enable"}</button>
                <button type="button" onClick={() => void api.evaluateAlert(rule.id).then(() => reload()).catch((error: unknown) => setMessage(error instanceof Error ? error.message : "Alert evaluation failed"))}>Evaluate</button>
                <button type="button" className="danger" onClick={() => void api.deleteAlert(rule.id).then(() => reload()).catch((error: unknown) => setMessage(error instanceof Error ? error.message : "Alert delete failed"))}>Delete</button>
              </div>
            </article>
          ))}
        </div>
        <div className="incident-list">
          {incidents.length === 0 ? <p>No incidents recorded.</p> : incidents.map((incident) => (
            <article className={`incident-row ${incident.status}`} key={incident.id}>
              <strong>{incident.ruleName ?? "Alert"}</strong>
              <span>{incident.status}: {incident.triggeringValue.toFixed(2)} / {incident.threshold}</span>
              <span>{formatDate(incident.openedAt)} {"->"} {formatDate(incident.resolvedAt)}</span>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
