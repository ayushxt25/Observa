"use client";

import { memo, useMemo, useState } from "react";
import { SERVICES } from "@/lib/types";
import { formatTime } from "@/lib/canvasUtils";
import type { HeatmapDatum } from "@/lib/visualization/types";

export const Heatmap = memo(function Heatmap({ cells }: { cells: HeatmapDatum[] }) {
  const [hover, setHover] = useState<string | null>(null);
  const buckets = useMemo(() => Array.from(new Set(cells.map((cell) => cell.bucketStart))).sort((a, b) => a - b), [cells]);
  const maxLatency = Math.max(1, ...cells.map((cell) => cell.avgLatency));
  const cellMap = useMemo(() => new Map(cells.map((cell) => [`${cell.service}:${cell.bucketStart}`, cell])), [cells]);

  return (
    <div className="heatmap-wrap">
      <div className="heatmap-grid" style={{ gridTemplateColumns: `110px repeat(${Math.max(1, buckets.length)}, minmax(18px, 1fr))` }}>
        <div className="heatmap-label">Service</div>
        {buckets.map((bucket) => <div key={bucket} className="heatmap-label tiny">{formatTime(bucket)}</div>)}
        {SERVICES.map((service) => (
          <div className="heatmap-row-label" key={service}>{service}</div>
        )).flatMap((label, serviceIndex) => {
          const service = SERVICES[serviceIndex];
          return [label, ...buckets.map((bucket) => {
            const cell = cellMap.get(`${service}:${bucket}`);
            const intensity = cell ? cell.avgLatency / maxLatency : 0;
            return (
              <button
                type="button"
                key={`${service}-${bucket}`}
                className="heat-cell"
                style={{ backgroundColor: `rgba(57, 208, 255, ${0.08 + intensity * 0.82})` }}
                onMouseEnter={() => setHover(cell ? `${service} ${formatTime(bucket)}: ${cell.avgLatency.toFixed(1)} ms avg, ${cell.errorCount} errors` : `${service}: no points`)}
                onMouseLeave={() => setHover(null)}
                aria-label={`${service} latency bucket`}
              />
            );
          })];
        })}
      </div>
      <div className="legend"><span />Low latency <strong />High latency</div>
      {hover ? <div className="tooltip fixed-tip">{hover}</div> : null}
    </div>
  );
});
