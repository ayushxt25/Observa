"use client";

import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { downsampleLine, formatTime, reportChartRender, setupCanvas, type Size } from "@/lib/canvasUtils";
import { useChartRenderer } from "@/hooks/useChartRenderer";
import { calculateViewport } from "@/lib/rendering/viewport";
import type { TimeSeriesPoint } from "@/lib/visualization/types";

interface Props {
  points: TimeSeriesPoint[];
}

export const LineChart = memo(function LineChart({ points }: Props) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [size, setSize] = useState<Size>({ width: 640, height: 260 });
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState(0);
  const [hover, setHover] = useState<{ x: number; y: number; point: TimeSeriesPoint } | null>(null);
  const draggingRef = useRef<{ x: number; pan: number } | null>(null);

  const visible = useMemo(() => {
    if (points.length === 0) return [];
    const viewport = calculateViewport(points.length, zoom, pan);
    return points.slice(viewport.start, viewport.end);
  }, [pan, points, zoom]);

  const rendered = useMemo(() => downsampleLine(visible, size.width), [size.width, visible]);
  const yDomain = useMemo(() => {
    if (rendered.length === 0) return { min: 0, max: 1 };
    let min = Infinity;
    let max = -Infinity;
    for (const point of rendered) {
      min = Math.min(min, point.avg);
      max = Math.max(max, point.avg);
    }
    return { min, max: Math.max(max, min + 1) };
  }, [rendered]);
  const xDomain = useMemo(() => {
    const first = rendered[0]?.timestamp ?? 0;
    const last = rendered.at(-1)?.timestamp ?? first + 1;
    return { first, last: Math.max(last, first + 1) };
  }, [rendered]);
  const axisTicks = useMemo(() => {
    const ticks: Array<{ x: number; label: string }> = [];
    for (let i = 0; i <= 3; i += 1) {
      const timestamp = xDomain.first + ((xDomain.last - xDomain.first) * i) / 3;
      ticks.push({ x: (size.width * i) / 3, label: rendered.length > 0 ? formatTime(timestamp) : "--" });
    }
    return ticks;
  }, [rendered.length, size.width, xDomain]);
  const yTicks = useMemo(() => {
    const ticks: Array<{ y: number; label: string }> = [];
    const range = yDomain.max - yDomain.min;
    for (let i = 0; i <= 2; i += 1) {
      const value = yDomain.max - (range * i) / 2;
      ticks.push({ y: 10 + ((size.height - 22) * i) / 2, label: `${value.toFixed(0)} ms` });
    }
    return ticks;
  }, [size.height, yDomain]);

  const draw = useCallback(() => {
    const started = performance.now();
    const canvas = canvasRef.current;
    try {
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
      const range = Math.max(1, yDomain.max - yDomain.min);
      const timeRange = Math.max(1, xDomain.last - xDomain.first);
      ctx.strokeStyle = "#39d0ff";
      ctx.lineWidth = 2;
      ctx.beginPath();
      for (let i = 0; i < rendered.length; i += 1) {
        const point = rendered[i];
        const x = ((point.timestamp - xDomain.first) / timeRange) * width;
        const y = height - ((point.avg - yDomain.min) / range) * (height - 22) - 10;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();
    } finally {
      reportChartRender(performance.now() - started);
    }
  }, [rendered, size, xDomain, yDomain]);

  useChartRenderer(draw);

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
        aria-hidden="true"
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
      <svg className="chart-svg-overlay" viewBox={`0 0 ${size.width} ${size.height}`} role="img" aria-labelledby="latency-title latency-desc">
        <title id="latency-title">Latency over time chart</title>
        <desc id="latency-desc">Canvas line plot with SVG axes and pointer crosshair showing aggregated latency over the selected time range.</desc>
        <line className="svg-axis" x1="0" y1={size.height - 24} x2={size.width} y2={size.height - 24} />
        <line className="svg-axis" x1="36" y1="0" x2="36" y2={size.height} />
        {axisTicks.map((tick) => (
          <text className="svg-tick" x={tick.x} y={size.height - 6} key={`${tick.x}-${tick.label}`}>{tick.label}</text>
        ))}
        {yTicks.map((tick) => (
          <text className="svg-tick y" x="4" y={tick.y} key={`${tick.y}-${tick.label}`}>{tick.label}</text>
        ))}
        {hover ? <line className="svg-crosshair" x1={hover.x} y1="0" x2={hover.x} y2={size.height - 24} /> : null}
      </svg>
      <div className="axis-row"><span>{visible[0] ? formatTime(visible[0].timestamp) : "--"}</span><span>{visible.at(-1) ? formatTime(visible.at(-1)!.timestamp) : "--"}</span></div>
      {hover ? <div className="tooltip floating" style={{ left: hover.x + 16, top: hover.y + 44 }}>{formatTime(hover.point.timestamp)}<br />{hover.point.avg.toFixed(1)} ms</div> : null}
    </div>
  );
});
