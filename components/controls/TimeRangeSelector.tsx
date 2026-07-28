"use client";

import { useDataStream } from "@/hooks/useDataStream";
import type { TimeRange } from "@/lib/types";

const ranges: TimeRange[] = ["5m", "15m", "1h", "6h", "all"];

export function TimeRangeSelector() {
  const { timeRange, setTimeRange } = useDataStream();
  return (
    <section className="panel">
      <h2>Time range</h2>
      <div className="segmented">
        {ranges.map((range) => (
          <button className={range === timeRange ? "active" : ""} type="button" key={range} onClick={() => setTimeRange(range)}>{range}</button>
        ))}
      </div>
    </section>
  );
}
