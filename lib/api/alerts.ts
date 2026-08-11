import { ObservaApiClient } from "./client";
import { getObservaApiUrl } from "./config";
import type { AlertRule, AlertRuleDraft, Incident, IncidentImpact, IncidentNotificationSummary, IncidentTimeline, IncidentTimelineEvent } from "@/lib/alerts/types";

interface AlertListDto { alerts: AlertRule[] }
interface IncidentListDto { incidents: Incident[] }
interface NotificationSummaryDto { summary: IncidentNotificationSummary }

export function mapAlert(input: AlertRule): AlertRule {
  return { ...input, description: input.description ?? undefined, service: input.service ?? undefined, region: input.region ?? undefined, lastEvaluatedAt: input.lastEvaluatedAt ?? undefined, lastTriggeredAt: input.lastTriggeredAt ?? undefined, notificationChannelIds: input.notificationChannelIds ?? [] };
}

export function mapIncident(input: Incident): Incident {
  return { ...input, ruleName: input.ruleName ?? undefined, resolvedAt: input.resolvedAt ?? undefined };
}

export function mapIncidentTimelineEvent(input: IncidentTimelineEvent): IncidentTimelineEvent {
  return { ...input, sourceType: input.sourceType ?? undefined, sourceId: input.sourceId ?? undefined, actorType: input.actorType ?? undefined, metadata: input.metadata ?? {} };
}

export function mapIncidentTimeline(input: IncidentTimeline): IncidentTimeline {
  return { events: input.events.map(mapIncidentTimelineEvent), limited: input.limited };
}

export function mapIncidentImpact(input: IncidentImpact): IncidentImpact {
  return {
    ...input,
    rootService: input.rootService ? { ...input.rootService, serviceId: input.rootService.serviceId ?? undefined, displayName: input.rootService.displayName ?? undefined } : undefined,
    affectedServices: input.affectedServices.map((item) => ({ ...item, serviceId: item.serviceId ?? undefined, displayName: item.displayName ?? undefined })),
    reason: input.reason ?? undefined,
  };
}

export class AlertsApi {
  constructor(private readonly client = new ObservaApiClient({ baseUrl: getObservaApiUrl() })) {}

  async listAlerts(signal?: AbortSignal): Promise<AlertRule[]> {
    const response = await this.client.get<AlertListDto>("/api/v1/alerts", { signal });
    return response.alerts.map(mapAlert);
  }

  async createAlert(draft: AlertRuleDraft, signal?: AbortSignal): Promise<AlertRule> {
    return mapAlert(await this.client.post<AlertRule>("/api/v1/alerts", this.body(draft), { signal }));
  }

  async updateAlert(id: string, draft: Partial<AlertRuleDraft>, signal?: AbortSignal): Promise<AlertRule> {
    return mapAlert(await this.client.patch<AlertRule>(`/api/v1/alerts/${id}`, this.body(draft), { signal }));
  }

  async deleteAlert(id: string, signal?: AbortSignal): Promise<void> {
    await this.client.delete(`/api/v1/alerts/${id}`, { signal });
  }

  async evaluateAlert(id: string, signal?: AbortSignal): Promise<void> {
    await this.client.post(`/api/v1/alerts/${id}/evaluate`, {}, { signal });
  }

  async listIncidents(signal?: AbortSignal): Promise<Incident[]> {
    const response = await this.client.get<IncidentListDto>("/api/v1/incidents", { signal });
    return response.incidents.map(mapIncident).sort((a, b) => Number(a.status !== "firing") - Number(b.status !== "firing") || Date.parse(b.openedAt) - Date.parse(a.openedAt));
  }

  async getIncidentTimeline(id: string, signal?: AbortSignal): Promise<IncidentTimeline> {
    return mapIncidentTimeline(await this.client.get<IncidentTimeline>(`/api/v1/incidents/${id}/timeline`, { signal }));
  }

  async getIncidentImpact(id: string, signal?: AbortSignal): Promise<IncidentImpact> {
    return mapIncidentImpact(await this.client.get<IncidentImpact>(`/api/v1/incidents/${id}/impact`, { signal }));
  }

  async getIncidentNotificationSummary(id: string, signal?: AbortSignal): Promise<IncidentNotificationSummary> {
    return (await this.client.get<NotificationSummaryDto>(`/api/v1/incidents/${id}/notifications/summary`, { signal })).summary;
  }

  private body(draft: Partial<AlertRuleDraft>): Record<string, unknown> {
    return {
      ...draft,
      service: draft.service || undefined,
      region: draft.region || undefined,
    };
  }
}
