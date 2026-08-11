import type { InteractionMetric, InteractionType } from "@/lib/telemetry/types";

export function markInteractionStart(type: InteractionType): { type: InteractionType; start: number } {
  const start = performance.now();
  performance.mark(`observa:${type}:start`);
  return { type, start };
}

export function markInteractionEnd(interaction: { type: InteractionType; start: number }): InteractionMetric {
  const endMark = `observa:${interaction.type}:end`;
  const measureName = `observa:${interaction.type}:latency`;
  performance.mark(endMark);
  performance.measure(measureName, `observa:${interaction.type}:start`, endMark);
  const metric = { type: interaction.type, durationMs: performance.now() - interaction.start };
  performance.clearMarks(`observa:${interaction.type}:start`);
  performance.clearMarks(endMark);
  performance.clearMeasures(measureName);
  return metric;
}

export function measureSync<T>(fn: () => T): { value: T; durationMs: number } {
  const start = performance.now();
  const value = fn();
  return { value, durationMs: performance.now() - start };
}

