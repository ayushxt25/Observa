"use client";

import { useContext } from "react";
import { DataContext } from "@/components/providers/DataProvider";

export function useDataStream() {
  const context = useContext(DataContext);
  if (!context) {
    throw new Error("useDataStream must be used within DataProvider");
  }
  return context;
}
