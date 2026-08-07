import { RingBuffer } from "@/lib/ringBuffer";
import type { TelemetryEvent, TelemetrySnapshot } from "./types";

type Listener = () => void;

export class TelemetryStore {
  private buffer: RingBuffer<TelemetryEvent>;
  private listeners = new Set<Listener>();
  private snapshot: TelemetrySnapshot;

  constructor(capacity: number, initial: readonly TelemetryEvent[] = []) {
    this.buffer = new RingBuffer<TelemetryEvent>(capacity, initial);
    this.snapshot = {
      version: 0,
      retainedCount: this.buffer.size,
      totalReceived: initial.length,
      latestTimestamp: initial.at(-1)?.timestamp ?? null,
      capacity,
    };
  }

  subscribe(listener: Listener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  getSnapshot(): TelemetrySnapshot {
    return this.snapshot;
  }

  readAll(): TelemetryEvent[] {
    return this.buffer.toArray();
  }

  append(event: TelemetryEvent): void {
    this.appendBatch([event]);
  }

  appendBatch(events: readonly TelemetryEvent[]): void {
    if (events.length === 0) return;
    this.buffer.pushMany(events);
    this.updateSnapshot(events.length, events.at(-1)?.timestamp ?? this.snapshot.latestTimestamp);
  }

  reset(events: readonly TelemetryEvent[] = [], capacity = this.snapshot.capacity): void {
    this.buffer = new RingBuffer<TelemetryEvent>(capacity, events);
    this.snapshot = {
      version: this.snapshot.version + 1,
      retainedCount: this.buffer.size,
      totalReceived: events.length,
      latestTimestamp: events.at(-1)?.timestamp ?? null,
      capacity,
    };
    this.emit();
  }

  setCapacity(capacity: number): void {
    this.buffer = this.buffer.resize(capacity);
    this.snapshot = {
      ...this.snapshot,
      version: this.snapshot.version + 1,
      retainedCount: this.buffer.size,
      capacity,
    };
    this.emit();
  }

  private updateSnapshot(received: number, latestTimestamp: number | null): void {
    this.snapshot = {
      ...this.snapshot,
      version: this.snapshot.version + 1,
      retainedCount: this.buffer.size,
      totalReceived: this.snapshot.totalReceived + received,
      latestTimestamp,
    };
    this.emit();
  }

  private emit(): void {
    for (const listener of this.listeners) listener();
  }
}

