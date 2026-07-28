import { describe, expect, it } from "vitest";
import { calculateVirtualRange } from "@/lib/performanceUtils";

describe("calculateVirtualRange", () => {
  it("returns visible indexes with overscan and spacer heights", () => {
    const range = calculateVirtualRange(100, 20, 100, 60, 2);
    expect(range).toEqual({
      startIndex: 1,
      endIndex: 10,
      offsetTop: 20,
      offsetBottom: 1800,
    });
  });
});
