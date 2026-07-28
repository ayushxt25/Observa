"use client";

import { useTransition } from "react";
import { useDataStream } from "@/hooks/useDataStream";
import type { TimeRange } from "@/lib/types";

const ranges: TimeRange[] = ["5m", "15m", "1h", "6h", "all"];

export function TimeRangeSelector() {
  const { timeRange, setTimeRange } = useDataStream();
  const [isPending, startTransition] = useTransition();
  return (
    <section className="panel">
      <h2>Time range {isPending ? <span className="pending-badge">Updating...</span> : null}</h2>
      <div className="segmented">
        {ranges.map((range) => (
          <button
            className={range === timeRange ? "active" : ""}
            type="button"
            key={range}
            aria-pressed={range === timeRange}
            onClick={() => startTransition(() => setTimeRange(range))}
          >
            {range}
          </button>
        ))}
      </div>
    </section>
  );
}
