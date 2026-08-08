import { ObservaApiError } from "@/lib/api/client";
import { TelemetryApi } from "@/lib/api/telemetry";
import type { TelemetryEvent, TelemetrySourceStatus } from "./types";
import type { TelemetrySource } from "./source";

export interface RemoteTelemetrySourceOptions {
  api: TelemetryApi;
  pollIntervalMs?: number;
}

export class RemoteTelemetrySource implements TelemetrySource {
  readonly kind = "remote" as const;
  private listeners = new Set<(batch: readonly TelemetryEvent[]) => void>();
  private timer: ReturnType<typeof setInterval> | null = null;
  private abortController: AbortController | null = null;
  private inFlight = false;
  private paused = false;
  private generated = 0;
  private latestTimestamp: number | null = null;
  private state: TelemetrySourceStatus["state"] = "idle";
  private message: string | undefined;
  private readonly pollIntervalMs: number;

  constructor(private readonly options: RemoteTelemetrySourceOptions) {
    this.pollIntervalMs = options.pollIntervalMs ?? 5_000;
  }

  start(): void {
    if (this.timer) return;
    this.state = "connecting";
    void this.poll();
    this.timer = setInterval(() => {
      if (!this.paused) void this.poll();
    }, this.pollIntervalMs);
  }

  stop(): void {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
    this.abortController?.abort();
    this.abortController = null;
    this.inFlight = false;
    this.state = "idle";
  }

  pause(): void {
    this.paused = true;
  }

  resume(): void {
    this.paused = false;
    void this.poll();
  }

  reset(): void {
    this.latestTimestamp = null;
    this.generated = 0;
    void this.poll();
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
      running: this.timer !== null,
      paused: this.paused,
      intervalMs: this.pollIntervalMs,
      batchSize: 0,
      generated: this.generated,
      state: this.state,
      message: this.message,
    };
  }

  private async poll(): Promise<void> {
    if (this.inFlight) return;
    this.inFlight = true;
    this.abortController?.abort();
    const controller = new AbortController();
    this.abortController = controller;
    try {
      const start = this.latestTimestamp === null ? undefined : this.latestTimestamp;
      const events = await this.options.api.fetchEvents({ start, limit: 10_000, signal: controller.signal });
      if (controller.signal.aborted) return;
      this.state = "connected";
      this.message = undefined;
      if (events.length > 0) {
        this.latestTimestamp = events.at(-1)?.timestamp ?? this.latestTimestamp;
        this.generated += events.length;
        for (const listener of this.listeners) listener(events);
      }
    } catch (error) {
      if (controller.signal.aborted) return;
      this.state = "error";
      this.message = error instanceof ObservaApiError || error instanceof Error ? error.message : "Remote telemetry unavailable";
    } finally {
      if (this.abortController === controller) this.abortController = null;
      this.inFlight = false;
    }
  }
}
