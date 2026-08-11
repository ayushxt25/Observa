import type { DashboardWidgetConfig, ThresholdState } from "./types";

export function evaluateThreshold(value: number | null, widget: Pick<DashboardWidgetConfig, "thresholdWarning" | "thresholdCritical">): ThresholdState {
  if (value === null || Number.isNaN(value)) return "normal";
  if (widget.thresholdCritical !== undefined && value >= widget.thresholdCritical) return "critical";
  if (widget.thresholdWarning !== undefined && value >= widget.thresholdWarning) return "warning";
  return "normal";
}
