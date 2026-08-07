import { describe, expect, it } from "vitest";
import { calculateViewport } from "@/lib/rendering/viewport";
import { linearScale } from "@/lib/rendering/scales";

describe("viewport rendering helpers", () => {
  it("calculates pan and zoom windows", () => {
    expect(calculateViewport(100, 2, 0.5)).toEqual({ start: 25, end: 75 });
  });

  it("maps linear domains to ranges", () => {
    const scale = linearScale(0, 100, 0, 10);
    expect(scale(50)).toBe(5);
  });
});

