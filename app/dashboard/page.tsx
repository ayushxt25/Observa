import type { Metadata } from "next";
import { DashboardClient } from "@/components/dashboard/DashboardClient";
import { generateInitialTelemetry } from "@/lib/dataGenerator";

export const metadata: Metadata = {
  title: "PulseGrid | Real-time telemetry dashboard",
  description: "A high-performance canvas telemetry dashboard for distributed service monitoring.",
};

export default function DashboardPage() {
  const initial = generateInitialTelemetry(10_000, 42);
  return <DashboardClient initialData={initial.points} />;
}
