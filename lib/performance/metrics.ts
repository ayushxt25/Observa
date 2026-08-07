export interface MemoryPerformance extends Performance {
  memory?: { usedJSHeapSize: number };
}

export function readHeapUsage(): string {
  const memory = (performance as MemoryPerformance).memory;
  return memory ? `${(memory.usedJSHeapSize / 1024 / 1024).toFixed(1)} MB` : "Not supported";
}

export function reportChartRender(durationMs: number): void {
  window.dispatchEvent(new CustomEvent<{ durationMs: number }>("observa:chart-render", { detail: { durationMs } }));
}

