"use client";

import { useEffect, useRef, useState } from "react";
import { readHeapUsage } from "@/lib/performance/metrics";

export interface PerformanceMonitorState {
  fps: number;
  frameMs: number;
  chartRenderMs: number;
  longTasks: number;
  heap: string;
}

export function usePerformanceMonitor(): PerformanceMonitorState {
  const [state, setState] = useState<PerformanceMonitorState>({ fps: 0, frameMs: 0, chartRenderMs: 0, longTasks: 0, heap: "Not supported" });
  const frameSamplesRef = useRef<number[]>([]);
  const chartSamplesRef = useRef<number[]>([]);

  useEffect(() => {
    let frame = 0;
    let last = performance.now();
    let frames = 0;
    let previousFrame = last;
    const tick = (time: number) => {
      frames += 1;
      const duration = time - previousFrame;
      previousFrame = time;
      frameSamplesRef.current.push(duration);
      if (frameSamplesRef.current.length > 60) frameSamplesRef.current.shift();
      if (time - last >= 1000) {
        const samples = frameSamplesRef.current;
        const frameMs = samples.reduce((sum, sample) => sum + sample, 0) / Math.max(1, samples.length);
        setState((current) => ({ ...current, fps: Math.round((frames * 1000) / (time - last)), frameMs, heap: readHeapUsage() }));
        frames = 0;
        last = time;
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, []);

  useEffect(() => {
    const onChartRender: EventListener = (event) => {
      const customEvent = event as CustomEvent<{ durationMs: number }>;
      chartSamplesRef.current.push(customEvent.detail.durationMs);
      if (chartSamplesRef.current.length > 40) chartSamplesRef.current.shift();
      const chartRenderMs = chartSamplesRef.current.reduce((sum, sample) => sum + sample, 0) / Math.max(1, chartSamplesRef.current.length);
      setState((current) => ({ ...current, chartRenderMs }));
    };
    window.addEventListener("observa:chart-render", onChartRender);
    return () => window.removeEventListener("observa:chart-render", onChartRender);
  }, []);

  useEffect(() => {
    if (typeof PerformanceObserver === "undefined") return undefined;
    let observer: PerformanceObserver | null = null;
    try {
      observer = new PerformanceObserver((list) => setState((current) => ({ ...current, longTasks: current.longTasks + list.getEntries().length })));
      observer.observe({ type: "longtask", buffered: true });
    } catch {
      return undefined;
    }
    return () => observer?.disconnect();
  }, []);

  return state;
}
