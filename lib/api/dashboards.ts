import { ObservaApiClient } from "./client";
import { getObservaApiUrl } from "./config";
import type { DashboardConfig, DashboardWidgetConfig, WidgetDraft } from "@/lib/dashboards/types";

interface ApiDashboardWidget {
  id: string;
  dashboardId: string;
  title: string;
  type: DashboardWidgetConfig["type"];
  metric: DashboardWidgetConfig["metric"];
  service?: string | null;
  region?: string | null;
  aggregation: DashboardWidgetConfig["aggregation"];
  bucket: DashboardWidgetConfig["bucket"];
  timeRange: DashboardWidgetConfig["timeRange"];
  position: number;
  width: 1 | 2;
  height: 1 | 2;
  thresholdWarning?: number | null;
  thresholdCritical?: number | null;
}

interface ApiDashboard {
  id: string;
  name: string;
  description?: string | null;
  widgets: ApiDashboardWidget[];
}

interface ApiDashboardList {
  dashboards: ApiDashboard[];
}

function cleanNumber(value: number | undefined): number | undefined {
  return value === undefined || !Number.isFinite(value) ? undefined : value;
}

export function widgetToApiBody(widget: DashboardWidgetConfig): Record<string, unknown> {
  return {
    title: widget.title,
    type: widget.type,
    metric: widget.metric,
    service: widget.service || undefined,
    region: widget.region || undefined,
    aggregation: widget.aggregation,
    bucket: widget.bucket,
    timeRange: widget.timeRange,
    position: widget.position,
    width: widget.width,
    height: widget.height,
    thresholdWarning: cleanNumber(widget.thresholdWarning),
    thresholdCritical: cleanNumber(widget.thresholdCritical),
  };
}

export function mapApiDashboard(input: ApiDashboard): DashboardConfig {
  return {
    id: input.id,
    name: input.name,
    description: input.description ?? undefined,
    system: false,
    widgets: input.widgets
      .map((widget) => ({
        id: widget.id,
        dashboardId: widget.dashboardId,
        title: widget.title,
        type: widget.type,
        metric: widget.metric,
        service: widget.service ?? undefined,
        region: widget.region ?? undefined,
        aggregation: widget.aggregation,
        bucket: widget.bucket,
        timeRange: widget.timeRange,
        position: widget.position,
        width: widget.width,
        height: widget.height,
        thresholdWarning: widget.thresholdWarning ?? undefined,
        thresholdCritical: widget.thresholdCritical ?? undefined,
      }))
      .sort((left, right) => left.position - right.position || left.id.localeCompare(right.id)),
  };
}

function draftToBody(draft: WidgetDraft, position: number): Record<string, unknown> {
  return {
    ...draft,
    service: draft.service || undefined,
    region: draft.region || undefined,
    thresholdWarning: cleanNumber(draft.thresholdWarning),
    thresholdCritical: cleanNumber(draft.thresholdCritical),
    position,
    width: draft.type === "line" || draft.type === "heatmap" ? 2 : 1,
    height: 1,
  };
}

export class DashboardApi {
  constructor(private readonly client = new ObservaApiClient({ baseUrl: getObservaApiUrl() })) {}

  async list(signal?: AbortSignal): Promise<DashboardConfig[]> {
    const response = await this.client.get<ApiDashboardList>("/api/v1/dashboards", { signal });
    return response.dashboards.map(mapApiDashboard);
  }

  async create(name: string, signal?: AbortSignal): Promise<DashboardConfig> {
    return mapApiDashboard(await this.client.post<ApiDashboard>("/api/v1/dashboards", { name }, { signal }));
  }

  async rename(id: string, name: string, signal?: AbortSignal): Promise<DashboardConfig> {
    return mapApiDashboard(await this.client.patch<ApiDashboard>(`/api/v1/dashboards/${id}`, { name }, { signal }));
  }

  async delete(id: string, signal?: AbortSignal): Promise<void> {
    await this.client.delete(`/api/v1/dashboards/${id}`, { signal });
  }

  async addWidget(dashboard: DashboardConfig, draft: WidgetDraft, signal?: AbortSignal): Promise<DashboardWidgetConfig> {
    const body = draftToBody(draft, dashboard.widgets.length);
    const widget = await this.client.post<ApiDashboardWidget>(`/api/v1/dashboards/${dashboard.id}/widgets`, body, { signal });
    return mapApiDashboard({ id: dashboard.id, name: dashboard.name, description: dashboard.description, widgets: [widget] }).widgets[0];
  }

  async updateWidget(dashboardId: string, widget: DashboardWidgetConfig, signal?: AbortSignal): Promise<DashboardWidgetConfig> {
    const updated = await this.client.patch<ApiDashboardWidget>(`/api/v1/dashboards/${dashboardId}/widgets/${widget.id}`, widgetToApiBody(widget), { signal });
    return mapApiDashboard({ id: dashboardId, name: "", widgets: [updated] }).widgets[0];
  }

  async deleteWidget(dashboardId: string, widgetId: string, signal?: AbortSignal): Promise<void> {
    await this.client.delete(`/api/v1/dashboards/${dashboardId}/widgets/${widgetId}`, { signal });
  }
}
