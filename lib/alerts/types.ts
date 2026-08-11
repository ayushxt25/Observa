import type { MetricName, Region, ServiceId } from "@/lib/types";

export type AlertOperator = ">" | ">=" | "<" | "<=";
export type AlertState = "normal" | "firing";
export type IncidentStatus = "firing" | "resolved";
export type AlertAggregation = "avg" | "min" | "max" | "sum" | "count";
export type AlertBucket = "raw" | "1m" | "5m" | "1h";

export interface AlertRule {
  id: string;
  name: string;
  description?: string;
  metric: MetricName;
  service?: ServiceId;
  region?: Region;
  aggregation: AlertAggregation;
  bucket: AlertBucket;
  evaluationWindowSeconds: number;
  operator: AlertOperator;
  threshold: number;
  evaluationIntervalSeconds: number;
  cooldownSeconds: number;
  enabled: boolean;
  notificationChannelIds: string[];
  state: AlertState;
  lastEvaluatedAt?: string;
  lastTriggeredAt?: string;
}

export interface AlertRuleDraft {
  name: string;
  metric: MetricName;
  operator: AlertOperator;
  threshold: number;
  aggregation: AlertAggregation;
  bucket: AlertBucket;
  evaluationWindowSeconds: number;
  evaluationIntervalSeconds: number;
  cooldownSeconds: number;
  service?: ServiceId;
  region?: Region;
  enabled: boolean;
  notificationChannelIds?: string[];
}

export interface Incident {
  id: string;
  alertRuleId: string;
  ruleName?: string;
  status: IncidentStatus;
  openedAt: string;
  resolvedAt?: string;
  triggeringValue: number;
  threshold: number;
  message: string;
}

export type IncidentTimelineEventType = "incident.opened" | "incident.resolved" | "notification.delivered" | "notification.failed" | string;

export interface IncidentTimelineEvent {
  id: string;
  incidentId: string;
  eventType: IncidentTimelineEventType;
  sourceType?: string;
  sourceId?: string;
  actorType?: string;
  title: string;
  metadata: Record<string, unknown>;
  occurredAt: string;
}

export interface IncidentTimeline {
  events: IncidentTimelineEvent[];
  limited: boolean;
}

export interface IncidentImpactService {
  serviceId?: string;
  name: string;
  displayName?: string;
  depth: number;
  impactStatus: "root_cause" | "affected";
}

export interface IncidentImpactEdge {
  id: string;
  sourceServiceId: string;
  targetServiceId: string;
  sourceServiceName: string;
  targetServiceName: string;
  dependencyType: string;
}

export interface IncidentImpact {
  rootService?: IncidentImpactService;
  affectedServices: IncidentImpactService[];
  dependencyEdges: IncidentImpactEdge[];
  affectedCount: number;
  maxDepth: number;
  impactUnavailable: boolean;
  reason?: string;
}

export interface IncidentNotificationSummary {
  pending: number;
  delivering: number;
  delivered: number;
  failed: number;
}
