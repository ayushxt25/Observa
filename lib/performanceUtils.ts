import type { VirtualRange } from "./types";

export function calculateVirtualRange(totalRows: number, rowHeight: number, viewportHeight: number, scrollTop: number, overscan: number): VirtualRange {
  const safeRowHeight = Math.max(1, rowHeight);
  const startIndex = Math.max(0, Math.floor(scrollTop / safeRowHeight) - overscan);
  const visibleCount = Math.ceil(viewportHeight / safeRowHeight) + overscan * 2;
  const endIndex = Math.min(totalRows, startIndex + visibleCount);
  return {
    startIndex,
    endIndex,
    offsetTop: startIndex * safeRowHeight,
    offsetBottom: Math.max(0, (totalRows - endIndex) * safeRowHeight),
  };
}

export function now(): number {
  return typeof performance !== "undefined" ? performance.now() : Date.now();
}
