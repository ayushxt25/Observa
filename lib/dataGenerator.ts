import { REGIONS, SERVICES, type RegionName, type TelemetryPoint, type TelemetryStatus } from "./types";

const serviceBase: Record<string, { latency: number; throughput: number; cpu: number; memory: number; payload: number }> = {
  auth: { latency: 64, throughput: 950, cpu: 38, memory: 44, payload: 5 },
  checkout: { latency: 145, throughput: 520, cpu: 54, memory: 63, payload: 18 },
  search: { latency: 92, throughput: 1320, cpu: 61, memory: 58, payload: 11 },
  payments: { latency: 188, throughput: 310, cpu: 48, memory: 52, payload: 9 },
  inventory: { latency: 74, throughput: 690, cpu: 42, memory: 49, payload: 13 },
  notifications: { latency: 119, throughput: 430, cpu: 35, memory: 46, payload: 7 },
};

const regionBias: Record<RegionName, number> = {
  "us-east-1": 0.92,
  "us-west-2": 1,
  "eu-central-1": 1.08,
  "ap-south-1": 1.18,
};

export class SeededRandom {
  private state: number;

  constructor(seed: number) {
    this.state = seed >>> 0;
  }

  next(): number {
    this.state = (1664525 * this.state + 1013904223) >>> 0;
    return this.state / 4294967296;
  }

  range(min: number, max: number): number {
    return min + (max - min) * this.next();
  }

  pick<T>(items: readonly T[]): T {
    return items[Math.floor(this.next() * items.length)] ?? items[0];
  }
}

export interface GeneratorState {
  seed: number;
  sequence: number;
  timestamp: number;
}

export interface BatchResult {
  points: TelemetryPoint[];
  state: GeneratorState;
}

export function createInitialGeneratorState(seed = 42, timestamp = Date.now() - 1_000_000): GeneratorState {
  return { seed, sequence: 0, timestamp };
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function statusFrom(errorRate: number, latency: number): TelemetryStatus {
  if (errorRate > 4.5 || latency > 650) return "critical";
  if (errorRate > 1.4 || latency > 320) return "degraded";
  return "healthy";
}

export function generateTelemetryBatch(state: GeneratorState, count: number, intervalMs = 100): BatchResult {
  const random = new SeededRandom(state.seed + state.sequence * 97);
  const points: TelemetryPoint[] = new Array(count);
  let timestamp = state.timestamp;

  for (let i = 0; i < count; i += 1) {
    const sequence = state.sequence + i;
    timestamp += intervalMs;
    const service = SERVICES[sequence % SERVICES.length];
    const region = REGIONS[Math.floor(sequence / SERVICES.length) % REGIONS.length];
    const base = serviceBase[service] ?? serviceBase.auth;
    const wave = Math.sin(sequence / 58 + SERVICES.indexOf(service)) * 0.12;
    const regionMultiplier = regionBias[region];
    const anomaly = random.next() > 0.992 ? random.range(1.8, 4.5) : 1;
    const latency = clamp((base.latency * regionMultiplier * (1 + wave) + random.range(-12, 22)) * anomaly, 8, 1200);
    const throughput = clamp(base.throughput * (1 - wave * 0.45) + random.range(-80, 90) - (anomaly > 1 ? latency * 0.9 : 0), 10, 2500);
    const cpuUsage = clamp(base.cpu + throughput / 80 + random.range(-7, 8) + (anomaly > 1 ? 18 : 0), 2, 99);
    const memoryUsage = clamp(base.memory + Math.sin(sequence / 280) * 7 + random.range(-4, 5), 8, 98);
    const errorRate = clamp(random.range(0.02, 0.65) + (anomaly > 1 ? random.range(1.4, 8.5) : 0) + latency / 1800, 0, 15);
    const payloadSize = clamp(base.payload * 1024 + random.range(-900, 2200) + latency * 8, 256, 120_000);

    points[i] = {
      id: `${timestamp}-${sequence}`,
      timestamp,
      service,
      region,
      latency: Math.round(latency * 10) / 10,
      throughput: Math.round(throughput),
      cpuUsage: Math.round(cpuUsage * 10) / 10,
      memoryUsage: Math.round(memoryUsage * 10) / 10,
      errorRate: Math.round(errorRate * 100) / 100,
      payloadSize: Math.round(payloadSize),
      status: statusFrom(errorRate, latency),
    };
  }

  return {
    points,
    state: { seed: state.seed, sequence: state.sequence + count, timestamp },
  };
}

export function generateInitialTelemetry(count: number, seed = 42): BatchResult {
  const start = Date.now() - count * 100;
  return generateTelemetryBatch(createInitialGeneratorState(seed, start), count, 100);
}
