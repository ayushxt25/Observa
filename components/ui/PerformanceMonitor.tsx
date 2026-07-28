"use client";

import { memo, useEffect, useRef, useState } from "react";
import { useDataStream } from "@/hooks/useDataStream";

interface MemoryPerformance extends Performance {
  memory?: { usedJSHeapSize: number };
}

export const PerformanceMonitor = memo(function PerformanceMonitor() {
  const { summary, capacity, dataProcessingDurationMs, latestInteraction } = useDataStream();
  const [fps, setFps] = useState(0);
  const [frameMs, setFrameMs] = useState(0);
  const [chartRenderMs, setChartRenderMs] = useState(0);
  const [longTasks, setLongTasks] = useState(0);
  const [heap, setHeap] = useState<string>("Not supported");
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
        setFps(Math.round((frames * 1000) / (time - last)));
        const samples = frameSamplesRef.current;
        const average = samples.reduce((sum, sample) => sum + sample, 0) / Math.max(1, samples.length);
        setFrameMs(average);
        frames = 0;
        last = time;
        const memory = (performance as MemoryPerformance).memory;
        setHeap(memory ? `${(memory.usedJSHeapSize / 1024 / 1024).toFixed(1)} MB` : "Not supported");
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
      const samples = chartSamplesRef.current;
      setChartRenderMs(samples.reduce((sum, sample) => sum + sample, 0) / Math.max(1, samples.length));
    };
    window.addEventListener("pulsegrid:chart-render", onChartRender);
    return () => window.removeEventListener("pulsegrid:chart-render", onChartRender);
  }, []);

  useEffect(() => {
    if (typeof PerformanceObserver === "undefined") return undefined;
    let observer: PerformanceObserver | null = null;
    try {
      observer = new PerformanceObserver((list) => setLongTasks((count) => count + list.getEntries().length));
      observer.observe({ type: "longtask", buffered: true });
    } catch {
      return undefined;
    }
    return () => observer?.disconnect();
  }, []);

  return (
    <section className="panel perf-panel">
      <h2>Performance</h2>
      <span>FPS <strong>{fps}</strong></span>
      <span>Retained <strong>{summary.totalPoints.toLocaleString()}</strong></span>
      <span>Generated <strong>{summary.generatedPoints.toLocaleString()}</strong></span>
      <span>Capacity <strong>{capacity.toLocaleString()}</strong></span>
      <span>Heap <strong>{heap}</strong></span>
      <span>Long tasks <strong>{longTasks}</strong></span>
      <span>Frame avg <strong>{frameMs.toFixed(1)} ms</strong></span>
      <span>Chart render <strong>{chartRenderMs.toFixed(1)} ms</strong></span>
      <span>Data processing <strong>{dataProcessingDurationMs.toFixed(1)} ms</strong></span>
      <span>Interaction <strong>{latestInteraction ? `${latestInteraction.type} ${latestInteraction.durationMs.toFixed(1)} ms` : "Not measured"}</strong></span>
    </section>
  );
});
