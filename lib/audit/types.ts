export type AuditActorType = "user" | "api_key" | "system" | "celery";
export type AuditOutcome = "success" | "failure";

export interface AuditEvent {
  id: string;
  workspaceId: string;
  actorUserId: string | null;
  actorType: AuditActorType;
  action: string;
  resourceType: string;
  resourceId: string | null;
  outcome: AuditOutcome;
  ipAddress: string | null;
  userAgent: string | null;
  requestId: string | null;
  metadata: Record<string, unknown>;
  createdAt: string;
}

export interface AuditEventPage {
  events: AuditEvent[];
  nextCursor: string | null;
}
