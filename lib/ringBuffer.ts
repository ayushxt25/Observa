export class RingBuffer<T> {
  private values: Array<T | undefined>;
  private start = 0;
  private length = 0;

  constructor(private capacityValue: number, initial?: readonly T[]) {
    this.values = new Array<T | undefined>(capacityValue);
    if (initial) this.pushMany(initial);
  }

  get capacity(): number {
    return this.capacityValue;
  }

  get size(): number {
    return this.length;
  }

  push(item: T): T | undefined {
    const writeIndex = (this.start + this.length) % this.capacityValue;
    if (this.length < this.capacityValue) {
      this.values[writeIndex] = item;
      this.length += 1;
      return undefined;
    } else {
      const evicted = this.values[this.start];
      this.values[this.start] = item;
      this.start = (this.start + 1) % this.capacityValue;
      return evicted;
    }
  }

  pushMany(items: readonly T[]): T[] {
    const evicted: T[] = [];
    for (let i = 0; i < items.length; i += 1) {
      const item = this.push(items[i]);
      if (item !== undefined) evicted.push(item);
    }
    return evicted;
  }

  resize(capacity: number): RingBuffer<T> {
    return new RingBuffer<T>(capacity, this.toArray().slice(-capacity));
  }

  clear(): void {
    this.values = new Array<T | undefined>(this.capacityValue);
    this.start = 0;
    this.length = 0;
  }

  at(index: number): T | undefined {
    if (index < 0 || index >= this.length) return undefined;
    return this.values[(this.start + index) % this.capacityValue];
  }

  toArray(): T[] {
    const out = new Array<T>(this.length);
    for (let i = 0; i < this.length; i += 1) {
      const value = this.at(i);
      if (value !== undefined) out[i] = value;
    }
    return out;
  }
}
