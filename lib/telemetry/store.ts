import { RingBuffer } from "@/lib/ringBuffer";
import type { TelemetryEvent, TelemetrySnapshot } from "./types";

type Listener = () => void;

export class TelemetryStore {
  private buffer: RingBuffer<TelemetryEvent>;
  private ids: Set<string>;
  private listeners = new Set<Listener>();
  private snapshot: TelemetrySnapshot;

  constructor(capacity: number, initial: readonly TelemetryEvent[] = []) {
    this.buffer = new RingBuffer<TelemetryEvent>(capacity, initial);
    this.ids = new Set(this.buffer.toArray().map((event) => event.id));
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
    const accepted: TelemetryEvent[] = [];
    const incomingIds = new Set<string>();
    for (const event of events) {
      if (this.ids.has(event.id) || incomingIds.has(event.id)) continue;
      incomingIds.add(event.id);
      accepted.push(event);
    }
    if (accepted.length === 0) return;
    const evicted = this.buffer.pushMany(accepted);
    for (const event of evicted) this.ids.delete(event.id);
    for (const event of accepted) this.ids.add(event.id);
    this.updateSnapshot(accepted.length, accepted.at(-1)?.timestamp ?? this.snapshot.latestTimestamp);
  }

  reset(events: readonly TelemetryEvent[] = [], capacity = this.snapshot.capacity): void {
    this.buffer = new RingBuffer<TelemetryEvent>(capacity, events);
    this.ids = new Set(this.buffer.toArray().map((event) => event.id));
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
    this.ids = new Set(this.buffer.toArray().map((event) => event.id));
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
