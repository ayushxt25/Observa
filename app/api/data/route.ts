import { generateTelemetryBatch, createInitialGeneratorState } from "@/lib/dataGenerator";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const url = new URL(request.url);
  const batch = Math.min(1000, Math.max(1, Number(url.searchParams.get("batch") ?? 10)));
  const seed = Math.max(1, Number(url.searchParams.get("seed") ?? 42));
  const sequence = Math.max(0, Number(url.searchParams.get("sequence") ?? 0));
  const timestamp = Math.max(0, Number(url.searchParams.get("timestamp") ?? Date.now()));
  const result = generateTelemetryBatch({ ...createInitialGeneratorState(seed, timestamp), sequence }, batch, 100);
  return Response.json(result);
}
