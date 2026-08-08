"use client";

import { useDashboardControls, useTelemetryActions } from "@/hooks/useDashboardControls";

export function DashboardHeader() {
  const { isPaused, sourceKind, sourceStatus } = useDashboardControls();
  const { pause, resume, reset } = useTelemetryActions();
  const statusText = sourceKind === "remote"
    ? sourceStatus.state === "connected" ? "Backend connected" : sourceStatus.state === "error" ? "Backend unavailable" : "Backend connecting"
    : isPaused ? "Simulation paused" : "Simulation live";
  return (
    <header className="dashboard-header">
      <div>
        <p className="eyebrow">PulseGrid</p>
        <h1>Real-time distributed service telemetry</h1>
      </div>
      <div className="header-actions">
        <span className={sourceStatus.state === "error" ? "status paused" : isPaused ? "status paused" : "status live"} title={sourceStatus.message}>{statusText}</span>
        <button type="button" onClick={isPaused ? resume : pause}>{isPaused ? "Resume" : "Pause"}</button>
        <button type="button" onClick={reset}>Reset</button>
      </div>
    </header>
  );
}
