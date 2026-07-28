"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { setupCanvas, type Size } from "@/lib/canvasUtils";
import type { TelemetryPoint } from "@/lib/types";

export function ScatterPlot({ points }: { points: TelemetryPoint[] }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const frameRef = useRef<number | null>(null);
  const [size, setSize] = useState<Size>({ width: 520, height: 240 });
  const [hover, setHover] = useState<string | null>(null);

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = setupCanvas(canvas, size);
    if (!ctx) return;
    ctx.clearRect(0, 0, size.width, size.height);
    ctx.fillStyle = "#071016";
    ctx.fillRect(0, 0, size.width, size.height);
    const sampleStep = Math.max(1, Math.floor(points.length / 6000));
    const maxPayload = Math.max(1, ...points.map((point) => point.payloadSize));
    const maxLatency = Math.max(1, ...points.map((point) => point.latency));
    for (let i = 0; i < points.length; i += sampleStep) {
      const point = points[i];
      const x = (point.payloadSize / maxPayload) * (size.width - 20) + 10;
      const y = size.height - (point.latency / maxLatency) * (size.height - 20) - 10;
      ctx.fillStyle = point.status === "critical" ? "#fb7185" : point.status === "degraded" ? "#facc15" : "#38bdf8";
      ctx.fillRect(x, y, 2, 2);
    }
  }, [points, size]);

  useEffect(() => {
    frameRef.current = requestAnimationFrame(draw);
    return () => {
      if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);
    };
  }, [draw]);

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
        onPointerMove={(event) => {
          const rect = event.currentTarget.getBoundingClientRect();
          const maxPayload = Math.max(1, ...points.map((point) => point.payloadSize));
          const maxLatency = Math.max(1, ...points.map((point) => point.latency));
          const payload = ((event.clientX - rect.left) / rect.width) * maxPayload;
          const latency = (1 - (event.clientY - rect.top) / rect.height) * maxLatency;
          setHover(`${payload.toFixed(0)} bytes / ${latency.toFixed(0)} ms`);
        }}
        onPointerLeave={() => setHover(null)}
      />
      <div className="axis-row"><span>Payload size</span><span>Latency</span></div>
      {hover ? <div className="tooltip fixed-tip">{hover}</div> : null}
    </div>
  );
}
