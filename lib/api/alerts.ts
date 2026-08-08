import { ObservaApiClient } from "./client";
import { getObservaApiUrl } from "./config";
import type { AlertRule, AlertRuleDraft, Incident } from "@/lib/alerts/types";

interface AlertListDto { alerts: AlertRule[] }
interface IncidentListDto { incidents: Incident[] }

export function mapAlert(input: AlertRule): AlertRule {
  return { ...input, description: input.description ?? undefined, service: input.service ?? undefined, region: input.region ?? undefined, lastEvaluatedAt: input.lastEvaluatedAt ?? undefined, lastTriggeredAt: input.lastTriggeredAt ?? undefined };
}

export function mapIncident(input: Incident): Incident {
  return { ...input, ruleName: input.ruleName ?? undefined, resolvedAt: input.resolvedAt ?? undefined };
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

  private body(draft: Partial<AlertRuleDraft>): Record<string, unknown> {
    return {
      ...draft,
      service: draft.service || undefined,
      region: draft.region || undefined,
    };
  }
}
