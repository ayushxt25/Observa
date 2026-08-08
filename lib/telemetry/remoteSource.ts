import { ObservaApiError } from "@/lib/api/client";
import { TelemetryStreamClient } from "@/lib/api/stream";
import { TelemetryApi } from "@/lib/api/telemetry";
import type { TelemetryEvent, TelemetrySourceStatus } from "./types";
import type { TelemetrySource } from "./source";

export interface RemoteTelemetrySourceOptions {
  api: TelemetryApi;
  streamClient?: TelemetryStreamClient;
  pollIntervalMs?: number;
}

export class RemoteTelemetrySource implements TelemetrySource {
  readonly kind = "remote" as const;
  private listeners = new Set<(batch: readonly TelemetryEvent[]) => void>();
  private fallbackTimer: ReturnType<typeof setInterval> | null = null;
  private abortController: AbortController | null = null;
  private inFlight = false;
  private paused = false;
  private generated = 0;
  private latestTimestamp: number | null = null;
  private latestStreamId: string | null = null;
  private state: TelemetrySourceStatus["state"] = "idle";
  private message: string | undefined;
  private readonly pollIntervalMs: number;
  private readonly streamClient: TelemetryStreamClient;

  constructor(private readonly options: RemoteTelemetrySourceOptions) {
    this.pollIntervalMs = options.pollIntervalMs ?? 5_000;
    this.streamClient = options.streamClient ?? new TelemetryStreamClient();
  }

  start(): void {
    if (this.state !== "idle") return;
    this.state = "connecting";
    void this.hydrateThenStream();
  }

  stop(): void {
    this.stopFallback();
    this.streamClient.stop();
    this.abortController?.abort();
    this.abortController = null;
    this.inFlight = false;
    this.state = "idle";
  }

  pause(): void {
    this.paused = true;
    this.streamClient.stop();
    this.stopFallback();
  }

  resume(): void {
    this.paused = false;
    this.state = "reconnecting";
    void this.hydrateThenStream();
  }

  reset(): void {
    this.latestTimestamp = null;
    this.latestStreamId = null;
    this.generated = 0;
    this.state = "reconnecting";
    void this.hydrateThenStream();
  }

  async getServices(): Promise<string[]> {
    return this.options.api.fetchServices();
  }

  subscribe(listener: (batch: readonly TelemetryEvent[]) => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  getStatus(): TelemetrySourceStatus {
    return {
      kind: this.kind,
      running: this.state !== "idle",
      paused: this.paused,
      intervalMs: this.pollIntervalMs,
      batchSize: 0,
      generated: this.generated,
      state: this.state,
      message: this.message,
    };
  }

  private async hydrateThenStream(): Promise<void> {
    if (this.inFlight || this.paused) return;
    this.inFlight = true;
    this.abortController?.abort();
    const controller = new AbortController();
    this.abortController = controller;
    try {
      const cursor = await this.options.api.fetchStreamCursor(controller.signal);
      const start = this.latestTimestamp === null ? undefined : this.latestTimestamp;
      const events = await this.options.api.fetchEvents({ start, limit: 10_000, signal: controller.signal });
      if (controller.signal.aborted || this.paused) return;
      this.emit(events);
      this.latestStreamId = cursor;
      this.startStream(cursor);
    } catch (error) {
      if (controller.signal.aborted) return;
      this.state = "degraded";
      this.message = error instanceof ObservaApiError || error instanceof Error ? error.message : "Remote telemetry unavailable";
      this.startFallback();
    } finally {
      if (this.abortController === controller) this.abortController = null;
      this.inFlight = false;
    }
  }

  private startStream(cursor: string): void {
    this.stopFallback();
    this.streamClient.start(cursor, {
      onOpen: () => {
        this.state = "connected";
        this.message = undefined;
      },
      onBatch: (batch, streamId) => {
        this.latestStreamId = streamId || this.latestStreamId;
        this.emit(batch);
      },
      onError: (message) => {
        if (this.paused || this.state === "idle") return;
        this.streamClient.stop();
        this.state = "reconnecting";
        this.message = message;
        this.startFallback();
      },
    });
  }

  private startFallback(): void {
    if (this.fallbackTimer || this.paused) return;
    this.fallbackTimer = setInterval(() => {
      void this.pollOnce();
    }, this.pollIntervalMs);
    void this.pollOnce();
  }

  private stopFallback(): void {
    if (this.fallbackTimer) clearInterval(this.fallbackTimer);
    this.fallbackTimer = null;
  }

  private async pollOnce(): Promise<void> {
    if (this.inFlight || this.paused) return;
    this.inFlight = true;
    const controller = new AbortController();
    this.abortController = controller;
    try {
      const start = this.latestTimestamp === null ? undefined : this.latestTimestamp;
      const events = await this.options.api.fetchEvents({ start, limit: 10_000, signal: controller.signal });
      if (controller.signal.aborted) return;
      this.emit(events);
      if (this.latestStreamId) this.startStream(this.latestStreamId);
      this.state = this.latestStreamId ? "reconnecting" : "degraded";
    } catch (error) {
      if (controller.signal.aborted) return;
      this.state = "degraded";
      this.message = error instanceof ObservaApiError || error instanceof Error ? error.message : "Remote telemetry unavailable";
    } finally {
      if (this.abortController === controller) this.abortController = null;
      this.inFlight = false;
    }
  }

  private emit(events: readonly TelemetryEvent[]): void {
    if (events.length === 0) return;
    this.latestTimestamp = events.at(-1)?.timestamp ?? this.latestTimestamp;
    this.generated += events.length;
    for (const listener of this.listeners) listener(events);
  }
}
