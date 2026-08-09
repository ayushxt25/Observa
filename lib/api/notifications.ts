import { ObservaApiClient } from "./client";
import { getObservaApiUrl } from "./config";
import type { NotificationChannel, NotificationChannelDraft, NotificationDelivery } from "@/lib/notifications/types";

interface ChannelListDto { channels: NotificationChannel[] }
interface DeliveryListDto { deliveries: NotificationDelivery[] }
interface TestDto { deliveryId: string; status: string }

export function mapNotificationChannel(input: NotificationChannel): NotificationChannel {
  return {
    ...input,
    emailConfig: input.emailConfig ?? undefined,
    webhookUrl: input.webhookUrl ?? undefined,
    webhookLabel: input.webhookLabel ?? undefined,
  };
}

export function mapNotificationDelivery(input: NotificationDelivery): NotificationDelivery {
  return {
    ...input,
    alertRuleId: input.alertRuleId ?? undefined,
    incidentId: input.incidentId ?? undefined,
    channelId: input.channelId ?? undefined,
    lastAttemptAt: input.lastAttemptAt ?? undefined,
    nextRetryAt: input.nextRetryAt ?? undefined,
    responseCode: input.responseCode ?? undefined,
    errorSummary: input.errorSummary ?? undefined,
    deliveredAt: input.deliveredAt ?? undefined,
  };
}

export class NotificationsApi {
  constructor(private readonly client = new ObservaApiClient({ baseUrl: getObservaApiUrl() })) {}

  async listChannels(signal?: AbortSignal): Promise<NotificationChannel[]> {
    const response = await this.client.get<ChannelListDto>("/api/v1/notification-channels", { signal });
    return response.channels.map(mapNotificationChannel);
  }

  async createChannel(draft: NotificationChannelDraft, signal?: AbortSignal): Promise<NotificationChannel> {
    return mapNotificationChannel(await this.client.post<NotificationChannel>("/api/v1/notification-channels", this.body(draft), { signal }));
  }

  async updateChannel(id: string, draft: Partial<NotificationChannelDraft>, signal?: AbortSignal): Promise<NotificationChannel> {
    return mapNotificationChannel(await this.client.patch<NotificationChannel>(`/api/v1/notification-channels/${id}`, this.body(draft), { signal }));
  }

  async deleteChannel(id: string, signal?: AbortSignal): Promise<void> {
    await this.client.delete(`/api/v1/notification-channels/${id}`, { signal });
  }

  async testChannel(id: string, signal?: AbortSignal): Promise<TestDto> {
    return this.client.post<TestDto>(`/api/v1/notification-channels/${id}/test`, {}, { signal });
  }

  async setAlertChannels(alertId: string, channelIds: string[], signal?: AbortSignal): Promise<void> {
    await this.client.put(`/api/v1/alerts/${alertId}/notification-channels`, { channelIds }, { signal });
  }

  async listDeliveries(signal?: AbortSignal): Promise<NotificationDelivery[]> {
    const response = await this.client.get<DeliveryListDto>("/api/v1/notification-deliveries", { signal });
    return response.deliveries.map(mapNotificationDelivery);
  }

  private body(draft: Partial<NotificationChannelDraft>): Record<string, unknown> {
    if (draft.type === "email") {
      return {
        name: draft.name,
        type: "email",
        enabled: draft.enabled,
        emailConfig: { recipients: (draft.recipients ?? "").split(",").map((item) => item.trim()).filter(Boolean) },
      };
    }
    const webhookConfig: Record<string, unknown> = { targetUrl: draft.targetUrl, label: draft.name };
    if (draft.webhookSecret) webhookConfig.secret = draft.webhookSecret;
    return { name: draft.name, type: "webhook", enabled: draft.enabled, webhookConfig };
  }
}
