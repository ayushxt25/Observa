export type NotificationChannelType = "email" | "webhook";
export type NotificationDeliveryStatus = "pending" | "delivering" | "delivered" | "failed";
export type NotificationEventType = "firing" | "resolved" | "test";

export interface NotificationChannel {
  id: string;
  workspaceId: string;
  name: string;
  type: NotificationChannelType;
  enabled: boolean;
  emailConfig?: { recipients: string[] };
  webhookUrl?: string;
  webhookLabel?: string;
  hasSecret: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface NotificationChannelDraft {
  name: string;
  type: NotificationChannelType;
  enabled: boolean;
  recipients: string;
  targetUrl: string;
  webhookSecret?: string;
}

export interface NotificationDelivery {
  id: string;
  alertRuleId?: string;
  incidentId?: string;
  channelId?: string;
  channelName: string;
  channelType: NotificationChannelType;
  eventType: NotificationEventType;
  status: NotificationDeliveryStatus;
  attemptCount: number;
  lastAttemptAt?: string;
  nextRetryAt?: string;
  responseCode?: number;
  errorSummary?: string;
  createdAt: string;
  deliveredAt?: string;
}
