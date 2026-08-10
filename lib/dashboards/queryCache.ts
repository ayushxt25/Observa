export { buildWidgetQueryKey as buildMetricQueryKey } from "@/lib/query/mapping";

type CacheEntry<T> = { expiresAt: number; promise: Promise<T>; controller: AbortController };

export class QueryCache<T> {
  private readonly entries = new Map<string, CacheEntry<T>>();

  constructor(private readonly ttlMs = 10_000, private readonly maxEntries = 32) {}

  get(key: string, load: (signal: AbortSignal) => Promise<T>): Promise<T> {
    const now = Date.now();
    const cached = this.entries.get(key);
    if (cached && cached.expiresAt > now) return cached.promise;
    const controller = new AbortController();
    const promise = load(controller.signal).catch((error: unknown) => {
      const current = this.entries.get(key);
      if (current?.promise === promise) this.entries.delete(key);
      throw error;
    }).finally(() => {
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
