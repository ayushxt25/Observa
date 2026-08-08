import type { MetricQueryKey } from "./types";

type CacheEntry<T> = { expiresAt: number; promise: Promise<T>; controller: AbortController };

export function buildMetricQueryKey(query: MetricQueryKey): string {
  return JSON.stringify({
    metric: query.metric,
    aggregation: query.aggregation,
    bucket: query.bucket,
    service: query.service ?? "all",
    region: query.region ?? "all",
    timeRange: query.timeRange,
    sourceVersion: query.sourceVersion,
  });
}

export class QueryCache<T> {
  private readonly entries = new Map<string, CacheEntry<T>>();

  constructor(private readonly ttlMs = 10_000, private readonly maxEntries = 32) {}

  get(key: string, load: (signal: AbortSignal) => Promise<T>): Promise<T> {
    const now = Date.now();
    const cached = this.entries.get(key);
    if (cached && cached.expiresAt > now) return cached.promise;
    const controller = new AbortController();
    const promise = load(controller.signal).finally(() => {
      const current = this.entries.get(key);
      if (current?.promise === promise && current.expiresAt <= Date.now()) this.entries.delete(key);
    });
    this.entries.set(key, { expiresAt: now + this.ttlMs, promise, controller });
    this.trim();
    return promise;
  }

  clear(): void {
    for (const entry of this.entries.values()) entry.controller.abort();
    this.entries.clear();
  }

  private trim(): void {
    while (this.entries.size > this.maxEntries) {
      const first = this.entries.keys().next().value;
      if (typeof first !== "string") return;
      this.entries.get(first)?.controller.abort();
      this.entries.delete(first);
    }
  }
}
