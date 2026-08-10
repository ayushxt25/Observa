"use client";

import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { reportChartRender, setupCanvas, type Size } from "@/lib/canvasUtils";
import { throughputByService } from "@/lib/aggregation";
import { useChartRenderer } from "@/hooks/useChartRenderer";
import type { TelemetryPoint } from "@/lib/types";

export interface BarDatum {
  service: string;
  throughput: number;
  count: number;
}

export const BarChart = memo(function BarChart({ points, data: providedData }: { points?: TelemetryPoint[]; data?: BarDatum[] }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [size, setSize] = useState<Size>({ width: 520, height: 240 });
  const [hover, setHover] = useState<{ x: number; y: number; label: string } | null>(null);
  const data = useMemo(() => providedData ?? throughputByService(points ?? []), [points, providedData]);

  const draw = useCallback(() => {
    const started = performance.now();
    const canvas = canvasRef.current;
    try {
      if (!canvas) return;
      const ctx = setupCanvas(canvas, size);
      if (!ctx) return;
      ctx.clearRect(0, 0, size.width, size.height);
      ctx.fillStyle = "#071016";
      ctx.fillRect(0, 0, size.width, size.height);
      const max = Math.max(1, ...data.map((item) => item.throughput));
      const gap = 12;
      if (data.length === 0) return;
      const barWidth = (size.width - gap * (data.length + 1)) / data.length;
      data.forEach((item, index) => {
        const height = (item.throughput / max) * (size.height - 44);
        const x = gap + index * (barWidth + gap);
        const y = size.height - height - 24;
        ctx.fillStyle = "#5eead4";
        ctx.fillRect(x, y, barWidth, height);
        ctx.fillStyle = "#94a3b8";
        ctx.font = "11px sans-serif";
        ctx.fillText(item.service.slice(0, 6), x, size.height - 8);
      });
    } finally {
      reportChartRender(performance.now() - started);
    }
  }, [data, size]);

  useChartRenderer(draw);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return undefined;
    const observer = new ResizeObserver(([entry]) => setSize({ width: Math.max(240, entry.contentRect.width), height: Math.max(220, entry.contentRect.height) }));
    observer.observe(canvas);
    return () => observer.disconnect();
  }, []);

  return (
    <div className="chart-shell">
      <canvas
        ref={canvasRef}
        className="chart-canvas"
        role="img"
        aria-label="Throughput by service bar chart rendered on Canvas"
        onPointerMove={(event) => {
          const rect = event.currentTarget.getBoundingClientRect();
          const x = event.clientX - rect.left;
          const index = Math.floor((x / rect.width) * data.length);
          const item = data[index];
          setHover(item ? { x, y: event.clientY - rect.top, label: `${item.service}: ${item.throughput.toFixed(0)} rps` } : null);
        }}
        onPointerLeave={() => setHover(null)}
      />
      {hover ? <div className="tooltip floating" style={{ left: hover.x + 12, top: hover.y + 20 }}>{hover.label}</div> : null}
    </div>
  );
});
