"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { downsampleLine, formatTime, setupCanvas, type Size } from "@/lib/canvasUtils";
import type { AggregatedPoint } from "@/lib/types";

interface Props {
  points: AggregatedPoint[];
}

export function LineChart({ points }: Props) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const frameRef = useRef<number | null>(null);
  const [size, setSize] = useState<Size>({ width: 640, height: 260 });
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState(0);
  const [hover, setHover] = useState<{ x: number; y: number; point: AggregatedPoint } | null>(null);
  const draggingRef = useRef<{ x: number; pan: number } | null>(null);

  const visible = useMemo(() => {
    if (points.length === 0) return [];
    const windowSize = Math.max(20, Math.floor(points.length / zoom));
    const maxStart = Math.max(0, points.length - windowSize);
    const start = Math.min(maxStart, Math.max(0, Math.floor(pan * maxStart)));
    return points.slice(start, start + windowSize);
  }, [pan, points, zoom]);

  const rendered = useMemo(() => downsampleLine(visible, size.width), [size.width, visible]);

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = setupCanvas(canvas, size);
    if (!ctx) return;
    const { width, height } = size;
    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = "#071016";
    ctx.fillRect(0, 0, width, height);
    ctx.strokeStyle = "rgba(148, 163, 184, 0.18)";
    ctx.lineWidth = 1;
    for (let i = 0; i <= 4; i += 1) {
      const y = (height / 4) * i;
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(width, y);
      ctx.stroke();
    }
    if (rendered.length < 2) return;
    let min = Infinity;
    let max = -Infinity;
    for (const point of rendered) {
      min = Math.min(min, point.avg);
      max = Math.max(max, point.avg);
    }
    const range = Math.max(1, max - min);
    const first = rendered[0].timestamp;
    const last = rendered[rendered.length - 1].timestamp;
    const timeRange = Math.max(1, last - first);
    ctx.strokeStyle = "#39d0ff";
    ctx.lineWidth = 2;
    ctx.beginPath();
    for (let i = 0; i < rendered.length; i += 1) {
      const point = rendered[i];
      const x = ((point.timestamp - first) / timeRange) * width;
      const y = height - ((point.avg - min) / range) * (height - 22) - 10;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.stroke();
    if (hover) {
      ctx.strokeStyle = "rgba(255,255,255,0.5)";
      ctx.beginPath();
      ctx.moveTo(hover.x, 0);
      ctx.lineTo(hover.x, height);
      ctx.stroke();
    }
  }, [hover, rendered, size]);

  useEffect(() => {
    if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);
    frameRef.current = requestAnimationFrame(draw);
    return () => {
      if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);
    };
  }, [draw]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return undefined;
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      setSize({ width: Math.max(240, entry.contentRect.width), height: Math.max(220, entry.contentRect.height) });
    });
    observer.observe(canvas);
    return () => observer.disconnect();
  }, []);

  const nearestPoint = useCallback(
    (clientX: number, clientY: number) => {
      const canvas = canvasRef.current;
      if (!canvas || rendered.length === 0) return null;
      const rect = canvas.getBoundingClientRect();
      const x = clientX - rect.left;
      const index = Math.min(rendered.length - 1, Math.max(0, Math.round((x / rect.width) * (rendered.length - 1))));
      return { x, y: clientY - rect.top, point: rendered[index] };
    },
    [rendered],
  );

  return (
    <div className="chart-shell">
      <div className="chart-toolbar">
        <span>{visible.length.toLocaleString()} source / {rendered.length.toLocaleString()} rendered</span>
        <button type="button" onClick={() => { setZoom(1); setPan(0); }}>Reset view</button>
      </div>
      <canvas
        ref={canvasRef}
        className="chart-canvas"
        onWheel={(event) => {
          event.preventDefault();
          setZoom((current) => Math.min(12, Math.max(1, current + (event.deltaY < 0 ? 0.4 : -0.4))));
        }}
        onPointerDown={(event) => {
          draggingRef.current = { x: event.clientX, pan };
          event.currentTarget.setPointerCapture(event.pointerId);
        }}
        onPointerMove={(event) => {
          const nearest = nearestPoint(event.clientX, event.clientY);
          setHover(nearest);
          const drag = draggingRef.current;
          if (drag) setPan(Math.min(1, Math.max(0, drag.pan - (event.clientX - drag.x) / 500)));
        }}
        onPointerLeave={() => setHover(null)}
        onPointerUp={() => { draggingRef.current = null; }}
      />
      <div className="axis-row"><span>{visible[0] ? formatTime(visible[0].timestamp) : "--"}</span><span>{visible.at(-1) ? formatTime(visible.at(-1)!.timestamp) : "--"}</span></div>
      {hover ? <div className="tooltip floating" style={{ left: hover.x + 16, top: hover.y + 44 }}>{formatTime(hover.point.timestamp)}<br />{hover.point.avg.toFixed(1)} ms</div> : null}
    </div>
  );
}
