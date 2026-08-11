"use client";

import { useContext } from "react";
import { DashboardControlsContext, TelemetryActionsContext } from "@/components/providers/DataProvider";

export function useDashboardControls() {
  const controls = useContext(DashboardControlsContext);
  if (!controls) throw new Error("useDashboardControls must be used within DataProvider");
  return controls;
}

export function useTelemetryActions() {
  const actions = useContext(TelemetryActionsContext);
  if (!actions) throw new Error("useTelemetryActions must be used within DataProvider");
  return actions;
}

