import { getObservaApiUrl } from "./config";
import { mapApiEvent } from "./telemetry";
import type { ApiTelemetryStreamMessage } from "./types";
import type { TelemetryEvent } from "@/lib/types";

export interface TelemetryStreamHandlers {
  onBatch: (batch: readonly TelemetryEvent[], streamId: string) => void;
  onOpen: () => void;
  onError: (message: string) => void;
}

export class TelemetryStreamClient {
  private eventSource: EventSource | null = null;

  start(cursor: string, handlers: TelemetryStreamHandlers): void {
    this.stop();
    const baseUrl = getObservaApiUrl();
    if (!baseUrl) {
      handlers.onError("Remote API URL is not configured");
      return;
    }
    const url = new URL(`${baseUrl}/api/v1/telemetry/stream`);
    url.searchParams.set("cursor", cursor);
    const source = new EventSource(url.toString());
    this.eventSource = source;
    source.onopen = () => handlers.onOpen();
    source.addEventListener("telemetry", (event) => {
      const messageEvent = event as MessageEvent<string>;
      const payload = JSON.parse(messageEvent.data) as ApiTelemetryStreamMessage;
      if (!Array.isArray(payload.events)) return;
      handlers.onBatch(payload.events.map(mapApiEvent), messageEvent.lastEventId);
    });
    source.addEventListener("stream-error", (event) => {
      const messageEvent = event as MessageEvent<string>;
      if (messageEvent.data) {
        this.stop();
        handlers.onError(messageEvent.data);
      }
    });
    source.onerror = () => {
      this.stop();
      handlers.onError("Telemetry stream unavailable");
    };
  }

  stop(): void {
    this.eventSource?.close();
    this.eventSource = null;
  }
}
