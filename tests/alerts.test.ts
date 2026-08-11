import { describe, expect, it, vi } from "vitest";
import { ObservaApiClient, setApiAccessToken, setApiWorkspaceId } from "@/lib/api/client";
import { mapAlert, mapIncident, mapIncidentImpact, mapIncidentTimeline, AlertsApi } from "@/lib/api/alerts";
import { affectedServiceNames, formatDuration, incidentDurationMs, notificationSummaryText, timelineLabel } from "@/lib/alerts/intelligence";
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

  it("maps incident timeline and impact DTOs", () => {
    const timeline = mapIncidentTimeline({ limited: false, events: [{ id: "e1", incidentId: "i1", eventType: "incident.opened", title: "Opened", metadata: {}, occurredAt: "2026-01-01T00:00:00Z", sourceType: undefined }] });
    expect(timelineLabel(timeline.events[0])).toBe("Incident opened");
    const impact = mapIncidentImpact({
      rootService: { serviceId: "s1", name: "auth-service", depth: 0, impactStatus: "root_cause" },
      affectedServices: [
        { serviceId: "s1", name: "auth-service", depth: 0, impactStatus: "root_cause" },
        { serviceId: "s2", name: "api-gateway", displayName: "Gateway", depth: 1, impactStatus: "affected" },
      ],
      dependencyEdges: [],
      affectedCount: 2,
      maxDepth: 1,
      impactUnavailable: false,
    });
    expect(affectedServiceNames(impact)).toEqual(["auth-service", "Gateway"]);
  });
});

describe("incident intelligence helpers", () => {
  it("formats duration and notification summaries", () => {
    expect(formatDuration(65_000)).toBe("1m 5s");
    expect(incidentDurationMs({ id: "i1", alertRuleId: "a1", status: "resolved", openedAt: "2026-01-01T00:00:00Z", resolvedAt: "2026-01-01T00:01:00Z", triggeringValue: 1, threshold: 1, message: "m" })).toBe(60_000);
    expect(notificationSummaryText({ delivered: 2, failed: 1, pending: 1, delivering: 1 })).toBe("2 delivered / 1 failed / 2 pending");
  });
});

describe("AlertsApi incident intelligence", () => {
  it("uses authenticated workspace headers for incident detail calls", async () => {
    setApiAccessToken("access");
    setApiWorkspaceId("workspace-1");
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/timeline")) return new Response(JSON.stringify({ events: [], limited: false }), { status: 200, headers: { "Content-Type": "application/json" } });
      if (url.endsWith("/impact")) return new Response(JSON.stringify({ rootService: null, affectedServices: [], dependencyEdges: [], affectedCount: 0, maxDepth: 0, impactUnavailable: true }), { status: 200, headers: { "Content-Type": "application/json" } });
      return new Response(JSON.stringify({ summary: { pending: 0, delivering: 0, delivered: 0, failed: 0 } }), { status: 200, headers: { "Content-Type": "application/json" } });
    });
    const api = new AlertsApi(new ObservaApiClient({ baseUrl: "http://backend.test" }));
    await api.getIncidentTimeline("i1");
    await api.getIncidentImpact("i1");
    await api.getIncidentNotificationSummary("i1");
    expect(fetchMock).toHaveBeenCalledTimes(3);
    for (const call of fetchMock.mock.calls) {
      const init = call[1] as RequestInit;
      expect((init.headers as Record<string, string>).Authorization).toBe("Bearer access");
      expect((init.headers as Record<string, string>)["X-Workspace-Id"]).toBe("workspace-1");
    }
    vi.restoreAllMocks();
    setApiAccessToken(null);
    setApiWorkspaceId(null);
  });
});
