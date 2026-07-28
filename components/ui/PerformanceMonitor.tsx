"use client";

import { useEffect, useState } from "react";
import { useDataStream } from "@/hooks/useDataStream";

interface MemoryPerformance extends Performance {
  memory?: { usedJSHeapSize: number };
}

export function PerformanceMonitor() {
  const { summary, capacity } = useDataStream();
  const [fps, setFps] = useState(0);
  const [longTasks, setLongTasks] = useState(0);
  const [heap, setHeap] = useState<string>("Not supported");

  useEffect(() => {
    let frame = 0;
    let last = performance.now();
    let frames = 0;
    const tick = (time: number) => {
      frames += 1;
      if (time - last >= 1000) {
        setFps(Math.round((frames * 1000) / (time - last)));
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
    </section>
  );
}
