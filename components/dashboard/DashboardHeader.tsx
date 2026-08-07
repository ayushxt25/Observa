"use client";

import { useDashboardControls, useTelemetryActions } from "@/hooks/useDashboardControls";

export function DashboardHeader() {
  const { isPaused } = useDashboardControls();
  const { pause, resume, reset } = useTelemetryActions();
  return (
    <header className="dashboard-header">
      <div>
        <p className="eyebrow">PulseGrid</p>
        <h1>Real-time distributed service telemetry</h1>
      </div>
      <div className="header-actions">
        <span className={isPaused ? "status paused" : "status live"}>{isPaused ? "Paused" : "Live"}</span>
        <button type="button" onClick={isPaused ? resume : pause}>{isPaused ? "Resume" : "Pause"}</button>
        <button type="button" onClick={reset}>Reset</button>
      </div>
    </header>
  );
}
