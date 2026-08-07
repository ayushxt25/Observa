"use client";

import { memo, useDeferredValue, useEffect, useMemo, useRef, useState } from "react";
import { formatTime } from "@/lib/canvasUtils";
import { useTelemetryQuery } from "@/hooks/useTelemetryQuery";
import { useVirtualization } from "@/hooks/useVirtualization";

const rowHeight = 34;
const viewportHeight = 360;

export const DataTable = memo(function DataTable() {
  const { visiblePoints, snapshotVersion } = useTelemetryQuery();
  const [scrollTop, setScrollTop] = useState(0);
  const [tablePoints, setTablePoints] = useState(visiblePoints);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const latestPointsRef = useRef(visiblePoints);
  const deferredTablePoints = useDeferredValue(tablePoints);
  const points = useMemo(() => deferredTablePoints.slice().reverse(), [deferredTablePoints]);
  const range = useVirtualization(points.length, rowHeight, viewportHeight, scrollTop, 6);
  const rows = useMemo(() => points.slice(range.startIndex, range.endIndex), [points, range]);

  useEffect(() => {
    const node = scrollRef.current;
    if (!node) return undefined;
    const onScroll = () => setScrollTop(node.scrollTop);
    node.addEventListener("scroll", onScroll, { passive: true });
    return () => node.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    latestPointsRef.current = visiblePoints;
  }, [visiblePoints]);

  useEffect(() => {
    setTablePoints(latestPointsRef.current);
  }, [snapshotVersion]);

  return (
    <div className="table-wrap">
      <div className="table-meta">{rows.length} rendered / {points.length.toLocaleString()} total</div>
      <div className="telemetry-table header-row">
        <span>Timestamp</span><span>Service</span><span>Region</span><span>Latency</span><span>Throughput</span><span>Status</span>
      </div>
      <div className="table-viewport" ref={scrollRef} style={{ height: viewportHeight }}>
        <div style={{ height: range.offsetTop }} />
        {rows.map((point) => (
          <div className="telemetry-table data-row" key={point.id} style={{ height: rowHeight }}>
            <span>{formatTime(point.timestamp)}</span>
            <span>{point.service}</span>
            <span>{point.region}</span>
            <span>{point.latency.toFixed(1)} ms</span>
            <span>{point.throughput.toLocaleString()} rps</span>
            <span className={`pill ${point.status}`}>{point.status}</span>
          </div>
        ))}
        <div style={{ height: range.offsetBottom }} />
      </div>
    </div>
  );
});
