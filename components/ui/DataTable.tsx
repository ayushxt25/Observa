"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { formatTime } from "@/lib/canvasUtils";
import { calculateVirtualRange } from "@/lib/performanceUtils";
import { useDataStream } from "@/hooks/useDataStream";

const rowHeight = 34;
const viewportHeight = 360;

export function DataTable() {
  const { visiblePoints, tableVersion } = useDataStream();
  const [scrollTop, setScrollTop] = useState(0);
  const [tablePoints, setTablePoints] = useState(visiblePoints);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const latestPointsRef = useRef(visiblePoints);
  const points = useMemo(() => tablePoints.slice().reverse(), [tablePoints]);
  const range = calculateVirtualRange(points.length, rowHeight, viewportHeight, scrollTop, 6);
  const rows = points.slice(range.startIndex, range.endIndex);

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
  }, [tableVersion]);

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
}
