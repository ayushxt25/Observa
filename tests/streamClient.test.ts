import { afterEach, describe, expect, it, vi } from "vitest";
import { TelemetryStreamClient } from "@/lib/api/stream";
import { setApiAccessToken, setApiWorkspaceId } from "@/lib/api/client";

function streamResponse(payload: string): Response {
  const encoder = new TextEncoder();
  return new Response(new ReadableStream({
    start(controller) {
      controller.enqueue(encoder.encode(payload));
      controller.close();
    },
  }), { status: 200, headers: { "Content-Type": "text/event-stream" } });
}

describe("TelemetryStreamClient", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    setApiAccessToken(null);
    setApiWorkspaceId(null);
  });

  it("uses auth/workspace headers and maps streamed telemetry events", async () => {
    setApiAccessToken("access");
    setApiWorkspaceId("workspace-1");
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(streamResponse(
      "id: 10-0\nevent: telemetry\ndata: {\"events\":[{\"id\":\"e1\",\"timestamp\":\"2026-08-09T00:00:00Z\",\"service\":\"api-gateway\",\"region\":\"us-east\",\"latency\":1,\"throughput\":2,\"cpuUsage\":3,\"memoryUsage\":4,\"errorRate\":0,\"payloadSize\":10,\"status\":\"healthy\"}]}\n\n",
    ));
    const batches: string[] = [];
    new TelemetryStreamClient().start("9-0", {
      onOpen: () => undefined,
      onError: (message) => { throw new Error(message); },
      onBatch: (batch, streamId) => batches.push(`${streamId}:${batch[0]?.id}`),
    });
    await vi.waitFor(() => expect(batches).toEqual(["10-0:e1"]));
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer access");
    expect((init.headers as Record<string, string>)["X-Workspace-Id"]).toBe("workspace-1");
  });

  it("aborts the active stream on stop", async () => {
    setApiAccessToken("access");
    setApiWorkspaceId("workspace-1");
    let signal: AbortSignal | undefined;
    vi.spyOn(globalThis, "fetch").mockImplementation((_input: RequestInfo | URL, init?: RequestInit) => {
      signal = init?.signal ?? undefined;
      return new Promise<Response>(() => undefined);
    });

    const client = new TelemetryStreamClient();
    client.start("0-0", {
      onOpen: () => undefined,
      onError: () => undefined,
      onBatch: () => undefined,
    });
    await vi.waitFor(() => expect(signal).toBeDefined());
    client.stop();
    expect(signal?.aborted).toBe(true);
  });
});
