import { describe, expect, it, vi } from "vitest";

describe("API URL configuration", () => {
  it("uses configured public API URL", async () => {
    vi.stubEnv("NEXT_PUBLIC_OBSERVA_API_URL", "http://localhost:8001/");
    vi.resetModules();
    const { getObservaApiUrl } = await import("@/lib/api/config");
    expect(getObservaApiUrl()).toBe("http://localhost:8001");
    vi.unstubAllEnvs();
  });
});
