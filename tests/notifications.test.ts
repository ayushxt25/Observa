import { describe, expect, it } from "vitest";
import { mapNotificationChannel, mapNotificationDelivery } from "@/lib/api/notifications";

describe("notification DTO mapping", () => {
  it("normalizes optional channel fields without exposing secrets", () => {
    const channel = mapNotificationChannel({
      id: "c1",
      workspaceId: "w1",
      name: "Ops hook",
      type: "webhook",
      enabled: true,
      webhookUrl: "https://example.com/hook",
      hasSecret: true,
      createdAt: "2026-08-09T00:00:00Z",
      updatedAt: "2026-08-09T00:00:00Z",
    });

    expect(channel.hasSecret).toBe(true);
    expect(JSON.stringify(channel)).not.toContain("secret-value");
  });

  it("normalizes delivery optional fields", () => {
    const delivery = mapNotificationDelivery({
      id: "d1",
      channelName: "Ops",
      channelType: "email",
      eventType: "firing",
      status: "pending",
      attemptCount: 0,
      createdAt: "2026-08-09T00:00:00Z",
    });

    expect(delivery.errorSummary).toBeUndefined();
    expect(delivery.incidentId).toBeUndefined();
  });
});
