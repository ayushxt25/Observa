"use client";

import { useContext } from "react";
import { DashboardControlsContext, TelemetryActionsContext } from "@/components/providers/DataProvider";

// TODO: remove after any downstream callers migrate to useDashboardControls/useTelemetryActions/useTelemetryQuery.
export function useDataStream() {
  const controls = useContext(DashboardControlsContext);
  const actions = useContext(TelemetryActionsContext);
  if (!controls || !actions) {
    throw new Error("useDataStream must be used within DataProvider");
  }
  return { ...controls, ...actions };
}
