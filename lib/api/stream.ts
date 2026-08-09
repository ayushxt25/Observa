import { getObservaApiUrl } from "./config";
import { getApiAuthHeaders, refreshApiAccessToken } from "./client";
import { mapApiEvent } from "./telemetry";
import type { ApiTelemetryStreamMessage } from "./types";
import type { TelemetryEvent } from "@/lib/types";

export interface TelemetryStreamHandlers {
  onBatch: (batch: readonly TelemetryEvent[], streamId: string) => void;
  onOpen: () => void;
  onError: (message: string) => void;
}

function parseSseFrame(frame: string): { id: string; event: string; data: string } {
  let id = "";
  let event = "message";
  const data: string[] = [];
  for (const line of frame.split(/\r?\n/)) {
    if (!line || line.startsWith(":")) continue;
    const index = line.indexOf(":");
    const field = index === -1 ? line : line.slice(0, index);
    const value = index === -1 ? "" : line.slice(index + 1).replace(/^ /, "");
    if (field === "id") id = value;
    else if (field === "event") event = value;
    else if (field === "data") data.push(value);
  }
  return { id, event, data: data.join("\n") };
}

export class TelemetryStreamClient {
  private controller: AbortController | null = null;
  private active = false;

  start(cursor: string, handlers: TelemetryStreamHandlers): void {
    this.stop();
    this.active = true;
    void this.connect(cursor, handlers, false);
  }

  stop(): void {
    this.active = false;
    this.controller?.abort();
    this.controller = null;
  }

  private async connect(cursor: string, handlers: TelemetryStreamHandlers, retried: boolean): Promise<void> {
    const baseUrl = getObservaApiUrl();
    if (!baseUrl) {
      handlers.onError("Remote API URL is not configured");
      return;
    }
    const url = new URL(`${baseUrl}/api/v1/telemetry/stream`);
    url.searchParams.set("cursor", cursor);
    const controller = new AbortController();
    this.controller = controller;
    try {
      const response = await fetch(url.toString(), {
        credentials: "include",
        headers: { Accept: "text/event-stream", ...getApiAuthHeaders() },
        signal: controller.signal,
      });
      if (response.status === 401 && !retried) {
        const token = await refreshApiAccessToken(baseUrl);
        if (token && this.active) return this.connect(cursor, handlers, true);
      }
      if (!response.ok || !response.body) throw new Error(`Telemetry stream failed with ${response.status}`);
      handlers.onOpen();
      await this.read(response.body, handlers);
    } catch (error) {
      if (controller.signal.aborted || !this.active) return;
      handlers.onError(error instanceof Error ? error.message : "Telemetry stream unavailable");
    } finally {
      if (this.controller === controller) this.controller = null;
    }
  }

  private async read(body: ReadableStream<Uint8Array>, handlers: TelemetryStreamHandlers): Promise<void> {
    const reader = body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (this.active) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let boundary = buffer.indexOf("\n\n");
      while (boundary >= 0) {
        const frame = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        this.dispatch(frame, handlers);
        boundary = buffer.indexOf("\n\n");
      }
    }
  }

  private dispatch(frame: string, handlers: TelemetryStreamHandlers): void {
    const parsed = parseSseFrame(frame);
    if (parsed.event === "telemetry" && parsed.data) {
      const payload = JSON.parse(parsed.data) as ApiTelemetryStreamMessage;
      if (Array.isArray(payload.events)) handlers.onBatch(payload.events.map(mapApiEvent), parsed.id);
    } else if (parsed.event === "stream-error") {
      handlers.onError(parsed.data || "Telemetry stream unavailable");
    }
  }
}
