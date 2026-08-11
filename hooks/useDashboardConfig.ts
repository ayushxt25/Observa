"use client";

import { useContext } from "react";
import { DashboardConfigContext } from "@/components/providers/DashboardConfigProvider";

export function useDashboardConfig() {
  const context = useContext(DashboardConfigContext);
  if (!context) throw new Error("useDashboardConfig must be used within DashboardConfigProvider");
  return context;
}
