import { aggregateLatency, buildHeatmap, filterTelemetry } from "@/lib/aggregation";
import type { WorkerRequest, WorkerResponse } from "@/lib/types";

self.onmessage = (event: MessageEvent<WorkerRequest>) => {
  const request = event.data;
  const filtered = filterTelemetry(request.points, request.service, request.timeRange);
  const response: WorkerResponse = {
    id: request.id,
    type: request.type,
    points: aggregateLatency(filtered, request.mode),
    heatmap: buildHeatmap(filtered),
    processingStartedAt: request.processingStartedAt,
  };
  self.postMessage(response);
};
