import type { AggregatedPoint } from "./types";

export interface Size {
  width: number;
  height: number;
}

export function setupCanvas(canvas: HTMLCanvasElement, size: Size): CanvasRenderingContext2D | null {
  const ratio = window.devicePixelRatio || 1;
  canvas.width = Math.max(1, Math.floor(size.width * ratio));
  canvas.height = Math.max(1, Math.floor(size.height * ratio));
  canvas.style.width = `${size.width}px`;
  canvas.style.height = `${size.height}px`;
  const context = canvas.getContext("2d");
  if (!context) return null;
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  return context;
}

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

export function reportChartRender(durationMs: number): void {
  window.dispatchEvent(new CustomEvent<{ durationMs: number }>("pulsegrid:chart-render", { detail: { durationMs } }));
}
