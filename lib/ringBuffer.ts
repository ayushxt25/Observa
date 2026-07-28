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

  push(item: T): void {
    const writeIndex = (this.start + this.length) % this.capacityValue;
    if (this.length < this.capacityValue) {
      this.values[writeIndex] = item;
      this.length += 1;
    } else {
      this.values[this.start] = item;
      this.start = (this.start + 1) % this.capacityValue;
    }
  }

  pushMany(items: readonly T[]): void {
    for (let i = 0; i < items.length; i += 1) this.push(items[i]);
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
