import { createInitialGeneratorState, generateInitialTelemetry, generateTelemetryBatch, type GeneratorState } from "@/lib/dataGenerator";
import type { TelemetryEvent, TelemetrySourceStatus } from "./types";

export interface TelemetrySource {
  readonly kind: "simulation" | "remote";
  start(): void | Promise<void>;
  stop(): void | Promise<void>;
  subscribe(listener: (batch: readonly TelemetryEvent[]) => void): () => void;
  getStatus(): TelemetrySourceStatus;
}

export interface SimulationTelemetrySourceOptions {
  seed?: number;
  intervalMs?: number;
  batchSize?: number;
  startTimestamp?: number;
  initialSequence?: number;
  generated?: number;
}

export class SimulationTelemetrySource implements TelemetrySource {
  readonly kind = "simulation" as const;
  private listeners = new Set<(batch: readonly TelemetryEvent[]) => void>();
  private timer: ReturnType<typeof setInterval> | null = null;
  private paused = false;
  private generated = 0;
  private state: GeneratorState;
  private intervalMs: number;
  private batchSize: number;

  constructor(options: SimulationTelemetrySourceOptions = {}) {
    this.intervalMs = options.intervalMs ?? 100;
    this.batchSize = options.batchSize ?? 10;
    this.state = { ...createInitialGeneratorState(options.seed ?? 42, options.startTimestamp ?? Date.now()), sequence: options.initialSequence ?? 0 };
    this.generated = options.generated ?? 0;
  }

  static withInitialData(count: number, options: SimulationTelemetrySourceOptions = {}): { source: SimulationTelemetrySource; events: TelemetryEvent[] } {
    const seed = options.seed ?? 42;
    const initial = generateInitialTelemetry(count, seed);
    const source = new SimulationTelemetrySource({ ...options, seed, startTimestamp: initial.state.timestamp });
    source.state = initial.state;
    source.generated = initial.points.length;
    return { source, events: initial.points };
  }

  start(): void {
    if (this.timer) return;
    this.timer = setInterval(() => {
      if (this.paused) return;
      const result = generateTelemetryBatch(this.state, this.batchSize, this.intervalMs);
      this.state = result.state;
      this.generated += result.points.length;
      for (const listener of this.listeners) listener(result.points);
    }, this.intervalMs);
  }

  stop(): void {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
  }

  pause(): void {
    this.paused = true;
  }

  resume(): void {
    this.paused = false;
  }

  setBatchSize(batchSize: number): void {
    this.batchSize = batchSize;
  }

  reset(seed = 42, timestamp = Date.now(), sequence = 0, generated = 0): void {
    this.state = { ...createInitialGeneratorState(seed, timestamp), sequence };
    this.generated = generated;
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
      intervalMs: this.intervalMs,
      batchSize: this.batchSize,
      generated: this.generated,
    };
  }
}
