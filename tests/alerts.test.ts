import { describe, expect, it } from "vitest";
import { mapAlert, mapIncident } from "@/lib/api/alerts";
import { validateAlertDraft } from "@/lib/alerts/validation";
import type { AlertRuleDraft } from "@/lib/alerts/types";

const draft: AlertRuleDraft = {
  name: "High latency",
  metric: "latency",
  operator: ">=",
  threshold: 100,
  aggregation: "avg",
  bucket: "1m",
  evaluationWindowSeconds: 60,
  evaluationIntervalSeconds: 30,
  cooldownSeconds: 300,
  enabled: true,
};

describe("alert validation", () => {
  it("validates threshold, windows and bucket compatibility", () => {
    expect(validateAlertDraft(draft)).toBeNull();
    expect(validateAlertDraft({ ...draft, threshold: Number.NaN })).toContain("Threshold");
    expect(validateAlertDraft({ ...draft, evaluationIntervalSeconds: 0 })).toContain("interval");
    expect(validateAlertDraft({ ...draft, bucket: "5m", evaluationWindowSeconds: 60 })).toContain("bucket");
  });
});

describe("alert DTO mapping", () => {
  it("normalizes optional alert and incident fields", () => {
    const alert = mapAlert({
      id: "a1",
      ...draft,
      state: "normal",
      description: undefined,
      notificationChannelIds: [],
    });
    expect(alert.service).toBeUndefined();
    const incident = mapIncident({
      id: "i1",
      alertRuleId: "a1",
      status: "firing",
      openedAt: "2026-01-01T00:00:00Z",
      triggeringValue: 200,
      threshold: 100,
      message: "firing",
    });
    expect(incident.resolvedAt).toBeUndefined();
  });
});
