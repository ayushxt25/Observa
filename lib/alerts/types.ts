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
