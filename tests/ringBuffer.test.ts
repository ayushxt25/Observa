import { describe, expect, it } from "vitest";
import { RingBuffer } from "@/lib/ringBuffer";

describe("RingBuffer", () => {
  it("overwrites the oldest entries when capacity is reached", () => {
    const buffer = new RingBuffer<number>(3);
    buffer.pushMany([1, 2, 3, 4, 5]);
    expect(buffer.size).toBe(3);
    expect(buffer.toArray()).toEqual([3, 4, 5]);
  });
});
