"use client";

import { useEffect, useState } from "react";
import type { Size } from "@/lib/rendering/canvas";

export function useElementSize<T extends Element>(element: T | null, fallback: Size): Size {
  const [size, setSize] = useState<Size>(fallback);
  useEffect(() => {
    if (!element) return undefined;
    const observer = new ResizeObserver(([entry]) => {
      setSize({ width: Math.max(240, entry.contentRect.width), height: Math.max(220, entry.contentRect.height) });
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, [element]);
  return size;
}

