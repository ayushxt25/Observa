"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertsApi } from "@/lib/api/alerts";
import { AuditApi } from "@/lib/api/audit";
import { NotificationsApi } from "@/lib/api/notifications";
import { useAuth } from "@/components/providers/AuthProvider";
import { validateAlertDraft } from "@/lib/alerts/validation";
import type { AlertAggregation, AlertBucket, AlertOperator, AlertRule, AlertRuleDraft, Incident } from "@/lib/alerts/types";
import type { NotificationChannel, NotificationChannelDraft, NotificationDelivery } from "@/lib/notifications/types";
import type { AuditEvent } from "@/lib/audit/types";
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
  notificationChannelIds: [],
};

const initialChannelDraft: NotificationChannelDraft = {
  name: "Ops email",
  type: "email",
  enabled: true,
  recipients: "ops@example.com",
  targetUrl: "https://example.com/observa",
};

function formatDate(value?: string): string {
  return value ? new Date(value).toLocaleTimeString() : "--";
}

export function AlertsPanel() {
  const api = useMemo(() => new AlertsApi(), []);
  const auditApi = useMemo(() => new AuditApi(), []);
  const notificationsApi = useMemo(() => new NotificationsApi(), []);
  const auth = useAuth();
  const activeWorkspaceId = auth.activeWorkspace?.id;
  const [alerts, setAlerts] = useState<AlertRule[]>([]);
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [channels, setChannels] = useState<NotificationChannel[]>([]);
  const [deliveries, setDeliveries] = useState<NotificationDelivery[]>([]);
  const [auditEvents, setAuditEvents] = useState<AuditEvent[]>([]);
  const [draft, setDraft] = useState<AlertRuleDraft>(initialDraft);
  const [channelDraft, setChannelDraft] = useState<NotificationChannelDraft>(initialChannelDraft);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingChannelId, setEditingChannelId] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const canEdit = auth.activeWorkspace?.role !== "viewer";
  const canManageChannels = auth.activeWorkspace?.role === "owner" || auth.activeWorkspace?.role === "admin";
  const latestRequestRef = useRef(0);
  const pollingInFlightRef = useRef(false);

  const reload = useCallback(async (signal?: AbortSignal, skipIfPending = false) => {
    if (skipIfPending && pollingInFlightRef.current) return;
    pollingInFlightRef.current = true;
    const requestId = latestRequestRef.current + 1;
    latestRequestRef.current = requestId;
    try {
      const [rules, history, channelList, deliveryList, auditPage] = await Promise.all([api.listAlerts(signal), api.listIncidents(signal), notificationsApi.listChannels(signal), notificationsApi.listDeliveries(signal), auditApi.listEvents(signal, { limit: 40 }).catch(() => ({ events: [], nextCursor: null }))]);
      if (signal?.aborted || requestId !== latestRequestRef.current) return;
      setAlerts(rules);
      setIncidents(history);
      setChannels(channelList);
      setDeliveries(deliveryList);
      setAuditEvents(auditPage.events);
      setMessage(null);
    } catch (error) {
      if (signal?.aborted || requestId !== latestRequestRef.current) return;
      setMessage(error instanceof Error ? error.message : "Alerts unavailable");
    } finally {
      pollingInFlightRef.current = false;
    }
  }, [api, auditApi, notificationsApi]);

  useEffect(() => {
    const controller = new AbortController();
    const initial = window.setTimeout(() => {
      setAlerts([]);
      setIncidents([]);
      setChannels([]);
      setDeliveries([]);
      setAuditEvents([]);
      void reload(controller.signal);
    }, 0);
    const timer = window.setInterval(() => void reload(controller.signal, true), 10_000);
    return () => {
      controller.abort();
      window.clearTimeout(initial);
      window.clearInterval(timer);
    };
  }, [activeWorkspaceId, reload]);

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
      notificationChannelIds: rule.notificationChannelIds,
    });
  };

  const saveChannel = async () => {
    if (!channelDraft.name.trim()) {
      setMessage("Channel name is required");
      return;
    }
    try {
      if (editingChannelId) await notificationsApi.updateChannel(editingChannelId, channelDraft);
      else await notificationsApi.createChannel(channelDraft);
      setEditingChannelId(null);
      setChannelDraft(initialChannelDraft);
      await reload();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Channel save failed");
    }
  };

  const editChannel = (channel: NotificationChannel) => {
    setEditingChannelId(channel.id);
    setChannelDraft({
      name: channel.name,
      type: channel.type,
      enabled: channel.enabled,
      recipients: channel.emailConfig?.recipients.join(", ") ?? "",
      targetUrl: channel.webhookUrl ?? "",
    });
  };

  const toggleChannelSelection = (channelId: string) => {
    setDraft((current) => {
      const selected = new Set(current.notificationChannelIds ?? []);
      if (selected.has(channelId)) selected.delete(channelId);
      else selected.add(channelId);
      return { ...current, notificationChannelIds: Array.from(selected) };
    });
  };

  return (
    <section className="panel alerts-panel">
      <div className="section-heading"><h2>Alerts</h2><span>{message ?? `${alerts.length} rules / ${incidents.length} incidents / ${deliveries.length} deliveries / ${auditEvents.length} audit events`}</span></div>
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
        <fieldset className="channel-picker">
          <legend>Notify</legend>
          {channels.length === 0 ? <span>No channels</span> : channels.map((channel) => (
            <label key={channel.id}><input type="checkbox" checked={(draft.notificationChannelIds ?? []).includes(channel.id)} onChange={() => toggleChannelSelection(channel.id)} />{channel.name}</label>
          ))}
        </fieldset>
        <button type="button" disabled={!canEdit} onClick={() => void save()}>{editingId ? "Save alert" : "Create alert"}</button>
      </div>
      <div className="notification-panel">
        <div className="section-heading"><h3>Notification channels</h3><span>{channels.length} configured</span></div>
        <div className="alert-form">
          <label>Name<input aria-label="Notification channel name" value={channelDraft.name} onChange={(event) => setChannelDraft((current) => ({ ...current, name: event.target.value }))} /></label>
          <label>Type<select aria-label="Notification channel type" value={channelDraft.type} onChange={(event) => setChannelDraft((current) => ({ ...current, type: event.target.value as NotificationChannelDraft["type"] }))}><option value="email">email</option><option value="webhook">webhook</option></select></label>
          {channelDraft.type === "email" ? <label>Recipients<input aria-label="Email recipients" value={channelDraft.recipients} onChange={(event) => setChannelDraft((current) => ({ ...current, recipients: event.target.value }))} /></label> : <><label>Webhook URL<input aria-label="Webhook URL" value={channelDraft.targetUrl} onChange={(event) => setChannelDraft((current) => ({ ...current, targetUrl: event.target.value }))} /></label><label>Secret<input aria-label="Webhook secret" type="password" value={channelDraft.webhookSecret ?? ""} onChange={(event) => setChannelDraft((current) => ({ ...current, webhookSecret: event.target.value || undefined }))} /></label></>}
          <label>Enabled<select aria-label="Notification channel enabled" value={String(channelDraft.enabled)} onChange={(event) => setChannelDraft((current) => ({ ...current, enabled: event.target.value === "true" }))}><option value="true">enabled</option><option value="false">disabled</option></select></label>
          <button type="button" disabled={!canManageChannels} onClick={() => void saveChannel()}>{editingChannelId ? "Save channel" : "Create channel"}</button>
        </div>
        <div className="alert-list">
          {channels.length === 0 ? <p>No notification channels yet.</p> : channels.map((channel) => (
            <article className="alert-row" key={channel.id}>
              <strong>{channel.name}</strong>
              <span>{channel.type} / {channel.enabled ? "enabled" : "disabled"}{channel.hasSecret ? " / signed" : ""}</span>
              <span>{channel.type === "email" ? channel.emailConfig?.recipients.join(", ") : channel.webhookUrl}</span>
              <div>
                <button type="button" disabled={!canManageChannels} onClick={() => editChannel(channel)}>Edit</button>
                <button type="button" disabled={!canManageChannels} onClick={() => void notificationsApi.testChannel(channel.id).then(() => reload()).catch((error: unknown) => setMessage(error instanceof Error ? error.message : "Test failed"))}>Test</button>
                <button type="button" disabled={!canManageChannels} className="danger" onClick={() => void notificationsApi.deleteChannel(channel.id).then(() => reload()).catch((error: unknown) => setMessage(error instanceof Error ? error.message : "Channel delete failed"))}>Delete</button>
              </div>
            </article>
          ))}
        </div>
      </div>
      <div className="alerts-grid">
        <div className="alert-list">
          {alerts.length === 0 ? <p>No alert rules yet.</p> : alerts.map((rule) => (
            <article className={`alert-row ${rule.state}`} key={rule.id}>
              <strong>{rule.name}</strong>
              <span>{rule.metric} {rule.operator} {rule.threshold} / {rule.state} / {(rule.notificationChannelIds ?? []).length} channels</span>
              <span>Evaluated {formatDate(rule.lastEvaluatedAt)}</span>
              <div>
                <button type="button" disabled={!canEdit} onClick={() => edit(rule)}>Edit</button>
                <button type="button" disabled={!canEdit} onClick={() => void api.updateAlert(rule.id, { enabled: !rule.enabled }).then(() => reload()).catch((error: unknown) => setMessage(error instanceof Error ? error.message : "Alert update failed"))}>{rule.enabled ? "Disable" : "Enable"}</button>
                <button type="button" disabled={!canEdit} onClick={() => void api.evaluateAlert(rule.id).then(() => reload()).catch((error: unknown) => setMessage(error instanceof Error ? error.message : "Alert evaluation failed"))}>Evaluate</button>
                <button type="button" disabled={!canEdit} className="danger" onClick={() => void api.deleteAlert(rule.id).then(() => reload()).catch((error: unknown) => setMessage(error instanceof Error ? error.message : "Alert delete failed"))}>Delete</button>
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
        <div className="incident-list">
          {deliveries.length === 0 ? <p>No notification deliveries recorded.</p> : deliveries.map((delivery) => (
            <article className={`incident-row ${delivery.status}`} key={delivery.id}>
              <strong>{delivery.channelName}</strong>
              <span>{delivery.eventType}: {delivery.status} / {delivery.attemptCount} attempts</span>
              <span>{delivery.errorSummary ?? formatDate(delivery.deliveredAt ?? delivery.createdAt)}</span>
            </article>
          ))}
        </div>
        <div className="incident-list audit-list">
          {auditEvents.length === 0 ? <p>No audit events recorded.</p> : auditEvents.map((event) => (
            <details className={`incident-row ${event.outcome}`} key={event.id}>
              <summary><strong>{humanAction(event.action)}</strong><span>{event.outcome} / {formatDate(event.createdAt)}</span></summary>
              <span>{event.actorType}{event.actorUserId ? ` / ${event.actorUserId.slice(0, 8)}` : ""}</span>
              <span>{event.resourceType}{event.resourceId ? ` / ${event.resourceId.slice(0, 8)}` : ""}</span>
              <pre>{JSON.stringify(event.metadata, null, 2)}</pre>
            </details>
          ))}
        </div>
      </div>
    </section>
  );
}

function humanAction(action: string): string {
  return action.split(".").map((part) => part.slice(0, 1).toUpperCase() + part.slice(1).replaceAll("_", " ")).join(" ");
}
