import argparse
import math
import os
import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

SERVICES = ["api-gateway", "auth-service", "billing-service", "search-service", "worker"]
REGIONS = ["us-east", "us-west", "eu-central", "ap-south"]


def build_event(index: int, rng: random.Random, started: datetime) -> dict[str, Any]:
    service = SERVICES[index % len(SERVICES)]
    region = REGIONS[(index // len(SERVICES)) % len(REGIONS)]
    wave = math.sin(index / 80)
    latency = max(8, 95 + wave * 28 + rng.uniform(-7, 7))
    error_rate = max(0, min(100, 0.35 + (latency - 95) / 180 + rng.uniform(-0.12, 0.25)))
    status = "critical" if error_rate > 2.2 or latency > 165 else "degraded" if error_rate > 1.0 else "healthy"
    return {
        "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"observa-seed-{started.isoformat()}-{index}")),
        "timestamp": (started + timedelta(milliseconds=index * 100)).isoformat(),
        "service": service,
        "region": region,
        "latency": round(latency, 3),
        "throughput": round(max(0, 900 + wave * 160 + rng.uniform(-50, 50)), 3),
        "cpuUsage": round(max(0, min(100, 48 + wave * 17 + rng.uniform(-8, 8))), 3),
        "memoryUsage": round(max(0, min(100, 55 + wave * 12 + rng.uniform(-5, 5))), 3),
        "errorRate": round(error_rate, 4),
        "payloadSize": int(max(128, 20_000 + wave * 4500 + rng.uniform(-2200, 2200))),
        "status": status,
    }


def chunks(events: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [events[index : index + size] for index in range(0, len(events), size)]


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate deterministic telemetry into Observa API.")
    parser.add_argument("--url", default="http://localhost:8000/api/v1/telemetry/batch")
    parser.add_argument("--api-key", default=os.environ.get("OBSERVA_API_KEY"))
    parser.add_argument("--count", type=int, default=10_000)
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    if not args.api_key:
        raise SystemExit("--api-key or OBSERVA_API_KEY is required")

    rng = random.Random(args.seed)
    started = datetime.now(timezone.utc) - timedelta(milliseconds=args.count * 100)
    events = [build_event(index, rng, started) for index in range(args.count)]

    accepted = 0
    with httpx.Client(timeout=30) as client:
        for batch in chunks(events, args.batch_size):
            response = client.post(args.url, json={"events": batch}, headers={"Authorization": f"Bearer {args.api_key}"})
            response.raise_for_status()
            accepted += int(response.json()["acceptedCount"])
    print(f"accepted={accepted} requested={args.count} url={args.url}")


if __name__ == "__main__":
    main()
