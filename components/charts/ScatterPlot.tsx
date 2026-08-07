"use client";

import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { reportChartRender, setupCanvas, type Size } from "@/lib/canvasUtils";
import { useChartRenderer } from "@/hooks/useChartRenderer";
import type { ScatterDatum } from "@/lib/visualization/types";

export const ScatterPlot = memo(function ScatterPlot({ points }: { points: ScatterDatum[] }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [size, setSize] = useState<Size>({ width: 520, height: 240 });
  const [hover, setHover] = useState<string | null>(null);
  const domain = useMemo(() => {
    let maxPayload = 1;
    let maxLatency = 1;
    for (const point of points) {
      maxPayload = Math.max(maxPayload, point.payloadSize);
      maxLatency = Math.max(maxLatency, point.latency);
    }
    return { maxPayload, maxLatency };
  }, [points]);

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
      const sampleStep = Math.max(1, Math.floor(points.length / 6000));
      for (let i = 0; i < points.length; i += sampleStep) {
        const point = points[i];
        const x = (point.payloadSize / domain.maxPayload) * (size.width - 20) + 10;
        const y = size.height - (point.latency / domain.maxLatency) * (size.height - 20) - 10;
        ctx.fillStyle = point.status === "critical" ? "#fb7185" : point.status === "degraded" ? "#facc15" : "#38bdf8";
        ctx.fillRect(x, y, 2, 2);
      }
    } finally {
      reportChartRender(performance.now() - started);
    }
  }, [domain, points, size]);

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
        aria-hidden="true"
        onPointerMove={(event) => {
          const rect = event.currentTarget.getBoundingClientRect();
          const payload = ((event.clientX - rect.left) / rect.width) * domain.maxPayload;
          const latency = (1 - (event.clientY - rect.top) / rect.height) * domain.maxLatency;
          setHover(`${payload.toFixed(0)} bytes / ${latency.toFixed(0)} ms`);
        }}
        onPointerLeave={() => setHover(null)}
      />
      <svg className="chart-svg-overlay" viewBox={`0 0 ${size.width} ${size.height}`} role="img" aria-labelledby="scatter-title scatter-desc">
        <title id="scatter-title">Payload size versus latency scatter plot</title>
        <desc id="scatter-desc">Canvas scatter plot with SVG axes and tick labels. Point color and text status labels identify healthy, degraded and critical telemetry.</desc>
        <line className="svg-axis" x1="28" y1={size.height - 24} x2={size.width} y2={size.height - 24} />
        <line className="svg-axis" x1="28" y1="0" x2="28" y2={size.height - 24} />
        <text className="svg-tick" x="30" y={size.height - 6}>0 B</text>
        <text className="svg-tick" x={size.width - 74} y={size.height - 6}>{`${Math.round(domain.maxPayload / 1024)} KB`}</text>
        <text className="svg-tick y" x="4" y="14">{`${Math.round(domain.maxLatency)} ms`}</text>
      </svg>
      <div className="axis-row"><span>Payload size</span><span>Latency</span></div>
      {hover ? <div className="tooltip fixed-tip">{hover}</div> : null}
    </div>
  );
});
