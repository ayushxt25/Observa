import { reportChartRender } from "./performance/metrics";
import type { AggregatedPoint } from "./types";
export { pointerPosition, setupCanvas, type Size } from "./rendering/canvas";

export function downsampleLine(points: readonly AggregatedPoint[], pixelWidth: number): AggregatedPoint[] {
  if (points.length <= pixelWidth * 2 || pixelWidth <= 0) return [...points];
  const bucketSize = Math.ceil(points.length / pixelWidth);
  const sampled: AggregatedPoint[] = [];
  for (let i = 0; i < points.length; i += bucketSize) {
    let min = points[i];
    let max = points[i];
    const end = Math.min(points.length, i + bucketSize);
    for (let j = i + 1; j < end; j += 1) {
      if (points[j].avg < min.avg) min = points[j];
      if (points[j].avg > max.avg) max = points[j];
    }
    if (min.timestamp < max.timestamp) {
      sampled.push(min, max);
    } else {
      sampled.push(max, min);
    }
  }
  return sampled.sort((a, b) => a.timestamp - b.timestamp);
}

export function formatTime(timestamp: number): string {
  return new Intl.DateTimeFormat("en", { hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(timestamp);
}

export function formatNumber(value: number, digits = 0): string {
  return new Intl.NumberFormat("en", { maximumFractionDigits: digits }).format(value);
}

export { reportChartRender };
