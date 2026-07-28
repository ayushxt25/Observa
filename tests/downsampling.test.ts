import { describe, expect, it } from "vitest";
import { downsampleLine } from "@/lib/canvasUtils";
import type { AggregatedPoint } from "@/lib/types";

function point(timestamp: number, avg: number): AggregatedPoint {
  return { timestamp, avg, min: avg, max: avg, count: 1 };
}

describe("downsampleLine", () => {
  it("reduces dense series while preserving bucket extrema", () => {
    const points = Array.from({ length: 100 }, (_, index) => point(index, index % 2 === 0 ? index : 100 - index));
    const result = downsampleLine(points, 10);
    expect(result.length).toBeLessThan(points.length);
    expect(result.some((item) => item.avg === 99)).toBe(true);
    expect(result.every((item, index, items) => index === 0 || item.timestamp >= items[index - 1].timestamp)).toBe(true);
  });
});
