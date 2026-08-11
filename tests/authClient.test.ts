import { afterEach, describe, expect, it, vi } from "vitest";
import { ObservaApiClient, setApiAccessToken, setApiAuthFailureHandler, setApiWorkspaceId } from "@/lib/api/client";

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

describe("ObservaApiClient auth coordination", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    setApiAccessToken(null);
    setApiWorkspaceId(null);
    setApiAuthFailureHandler(null);
  });

  it("attaches access token and workspace headers", async () => {
    setApiAccessToken("access-token");
    setApiWorkspaceId("workspace-1");
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(response({ ok: true }));
    await new ObservaApiClient({ baseUrl: "https://api.example.test" }).get("/api/v1/dashboards");
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer access-token");
    expect((init.headers as Record<string, string>)["X-Workspace-Id"]).toBe("workspace-1");
    expect(init.credentials).toBe("include");
  });

  it("deduplicates refresh and retries protected requests once", async () => {
    setApiAccessToken("expired");
    let refreshCount = 0;
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith("/api/v1/auth/refresh")) {
        refreshCount += 1;
        return response({ accessToken: "fresh" });
      }
      const auth = (init?.headers as Record<string, string> | undefined)?.Authorization;
      return auth === "Bearer fresh" ? response({ ok: true }) : response({ detail: "expired" }, 401);
    });
    const client = new ObservaApiClient({ baseUrl: "https://api.example.test" });
    const [left, right] = await Promise.all([client.get("/api/v1/dashboards"), client.get("/api/v1/alerts")]);
    expect(left).toEqual({ ok: true });
    expect(right).toEqual({ ok: true });
    expect(refreshCount).toBe(1);
    expect(fetchMock).toHaveBeenCalledTimes(5);
  });
});
