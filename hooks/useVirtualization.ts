"use client";

import { useMemo } from "react";
import { calculateVirtualRange } from "@/lib/performanceUtils";

export function useVirtualization(totalRows: number, rowHeight: number, viewportHeight: number, scrollTop: number, overscan: number) {
  return useMemo(() => calculateVirtualRange(totalRows, rowHeight, viewportHeight, scrollTop, overscan), [overscan, rowHeight, scrollTop, totalRows, viewportHeight]);
}

