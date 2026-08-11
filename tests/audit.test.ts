import { describe, expect, it } from "vitest";
import type { AuditEvent } from "@/lib/audit/types";

describe("audit types", () => {
  it("represents safe audit metadata without secrets", () => {
    const event: AuditEvent = {
      id: "event-1",
      workspaceId: "workspace-1",
      actorUserId: "user-1",
      actorType: "user",
      action: "dashboard.created",
      resourceType: "dashboard",
      resourceId: "dashboard-1",
      outcome: "success",
      ipAddress: null,
      userAgent: null,
      requestId: "request-1",
      metadata: { name: "Ops" },
      createdAt: new Date(0).toISOString(),
    };
    expect(event.action).toBe("dashboard.created");
    expect(event.metadata).toEqual({ name: "Ops" });
  });
});
