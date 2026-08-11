import type { AlertRuleDraft } from "./types";

const minEvaluationIntervalSeconds = 5;

export function validateAlertDraft(draft: AlertRuleDraft): string | null {
  if (!draft.name.trim()) return "Alert name is required";
  if (!Number.isFinite(draft.threshold) || draft.threshold < 0) return "Threshold must be a finite non-negative number";
  if (!Number.isInteger(draft.evaluationWindowSeconds) || draft.evaluationWindowSeconds <= 0) return "Evaluation window must be greater than zero";
  if (!Number.isInteger(draft.evaluationIntervalSeconds) || draft.evaluationIntervalSeconds < minEvaluationIntervalSeconds) return "Evaluation interval must be at least 5 seconds";
  if (!Number.isInteger(draft.cooldownSeconds) || draft.cooldownSeconds < 0) return "Cooldown cannot be negative";
  if (draft.bucket === "1m" && draft.evaluationWindowSeconds < 60) return "Window must cover at least one bucket";
  if (draft.bucket === "5m" && draft.evaluationWindowSeconds < 300) return "Window must cover at least one bucket";
  if (draft.bucket === "1h" && draft.evaluationWindowSeconds < 3600) return "Window must cover at least one bucket";
  return null;
}
