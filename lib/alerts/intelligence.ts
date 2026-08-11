import type { Incident, IncidentImpact, IncidentNotificationSummary, IncidentTimelineEvent } from "./types";

export function incidentDurationMs(incident: Incident, now = Date.now()): number {
  const start = Date.parse(incident.openedAt);
  const end = incident.resolvedAt ? Date.parse(incident.resolvedAt) : now;
  return Math.max(0, end - start);
}

export function formatDuration(ms: number): string {
  const seconds = Math.floor(ms / 1000);
  const minutes = Math.floor(seconds / 60);
  const hours = Math.floor(minutes / 60);
  if (hours > 0) return `${hours}h ${minutes % 60}m`;
  if (minutes > 0) return `${minutes}m ${seconds % 60}s`;
  return `${seconds}s`;
}

export function timelineLabel(event: IncidentTimelineEvent): string {
  if (event.eventType === "incident.opened") return "Incident opened";
  if (event.eventType === "incident.resolved") return "Incident resolved";
  if (event.eventType === "notification.delivered") return "Notification delivered";
  if (event.eventType === "notification.failed") return "Notification failed";
  return event.title || event.eventType;
}

export function notificationSummaryText(summary?: IncidentNotificationSummary): string {
  if (!summary) return "No notification summary";
  return `${summary.delivered} delivered / ${summary.failed} failed / ${summary.pending + summary.delivering} pending`;
}

export function affectedServiceNames(impact?: IncidentImpact): string[] {
  return impact?.affectedServices.map((service) => service.displayName || service.name) ?? [];
}
