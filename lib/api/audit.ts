import { ObservaApiClient } from "./client";
import { getObservaApiUrl } from "./config";
import type { AuditEventPage } from "@/lib/audit/types";

export class AuditApi {
  constructor(private readonly client = new ObservaApiClient({ baseUrl: getObservaApiUrl() })) {}

  listEvents(signal?: AbortSignal, params: { action?: string; outcome?: string; cursor?: string; limit?: number } = {}): Promise<AuditEventPage> {
    const search = new URLSearchParams();
    if (params.action) search.set("action", params.action);
    if (params.outcome) search.set("outcome", params.outcome);
    if (params.cursor) search.set("cursor", params.cursor);
    search.set("limit", String(params.limit ?? 50));
    return this.client.get<AuditEventPage>(`/api/v1/audit-events?${search.toString()}`, { signal });
  }
}
