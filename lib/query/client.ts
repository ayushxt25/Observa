import { ObservaApiClient } from "@/lib/api/client";
import type { TelemetryQueryRequest, TelemetryQueryResponse } from "./types";

export class QueryEngineApi {
  constructor(private readonly client: ObservaApiClient) {}

  async run(request: TelemetryQueryRequest, signal?: AbortSignal): Promise<TelemetryQueryResponse> {
    return this.client.post<TelemetryQueryResponse>("/api/v1/query", request, { signal });
  }
}
