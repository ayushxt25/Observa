"use client";

import { useEffect, useRef } from "react";

export function useChartRenderer(draw: () => void): void {
  const frameRef = useRef<number | null>(null);
  useEffect(() => {
    if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);
    frameRef.current = requestAnimationFrame(draw);
    return () => {
      if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);
    };
  }, [draw]);
}

