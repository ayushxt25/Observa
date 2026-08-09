import { describe, expect, it, vi } from "vitest";
import { ObservaApiClient, setApiAccessToken, setApiWorkspaceId } from "@/lib/api/client";
import { mapDependency, mapService, serviceDraftBody, servicePatchBody, ServicesApi } from "@/lib/api/services";
import { buildTopologyLayout, healthLabel, serviceMatchesFilters } from "@/lib/services/topology";
import type { ServiceCatalogItem, ServiceDependency } from "@/lib/services/types";

function service(id: string, name: string, health: ServiceCatalogItem["health"] = "healthy"): ServiceCatalogItem {
  return {
    id,
    workspaceId: "workspace-1",
    name,
    displayName: name.toUpperCase(),
    environment: "prod",
    tags: ["edge"],
    createdAt: "2026-08-09T00:00:00Z",
    updatedAt: "2026-08-09T00:00:00Z",
    health,
    recentEventCount: 10,
    activeAlertCount: 0,
    activeIncidentCount: 0,
  };
}

describe("service catalog mapping", () => {
  it("normalizes optional service and dependency fields", () => {
    const mapped = mapService({ ...service("s1", "api-gateway"), displayName: undefined, avgLatency: undefined });
    expect(mapped.displayName).toBeUndefined();
    expect(mapped.tags).toEqual(["edge"]);
    const dependency = mapDependency({
      id: "d1",
      workspaceId: "workspace-1",
      sourceServiceId: "s1",
      targetServiceId: "s2",
      dependencyType: "http",
      lastSeenAt: undefined,
      createdAt: "2026-08-09T00:00:00Z",
      updatedAt: "2026-08-09T00:00:00Z",
    });
    expect(dependency.lastSeenAt).toBeUndefined();
  });

  it("keeps canonical name out of patch bodies", () => {
    expect(serviceDraftBody({ name: "api-gateway", displayName: "Gateway", tags: ["Edge"] })).toMatchObject({ name: "api-gateway", tags: ["edge"] });
    expect(servicePatchBody({ displayName: "Gateway", tags: [] })).not.toHaveProperty("name");
  });
});

describe("service topology", () => {
  it("builds deterministic nodes and workspace edges", () => {
    const services = [service("s2", "auth-service", "degraded"), service("s1", "api-gateway")];
    const dependencies: ServiceDependency[] = [{
      id: "dep-1",
      workspaceId: "workspace-1",
      sourceServiceId: "s1",
      targetServiceId: "s2",
      dependencyType: "http",
      createdAt: "2026-08-09T00:00:00Z",
      updatedAt: "2026-08-09T00:00:00Z",
    }];
    const layout = buildTopologyLayout(services, dependencies);
    expect(layout.nodes.map((node) => node.id)).toEqual(["s1", "s2"]);
    expect(layout.edges).toHaveLength(1);
    expect(layout.edges[0].dependencyType).toBe("http");
  });

  it("filters by search, health, environment and tag", () => {
    const item = service("s1", "api-gateway", "critical");
    expect(serviceMatchesFilters(item, { search: "gateway", health: "critical", environment: "prod", tag: "edge" })).toBe(true);
    expect(serviceMatchesFilters(item, { search: "worker", health: "", environment: "", tag: "" })).toBe(false);
    expect(healthLabel("unknown")).toBe("Unknown");
  });

  it("lays out 100 services without dropping valid edges", () => {
    const services = Array.from({ length: 100 }, (_, index) => service(`s${index}`, `service-${index}`));
    const dependencies = Array.from({ length: 99 }, (_, index): ServiceDependency => ({
      id: `dep-${index}`,
      workspaceId: "workspace-1",
      sourceServiceId: `s${index}`,
      targetServiceId: `s${index + 1}`,
      dependencyType: "http",
      createdAt: "2026-08-09T00:00:00Z",
      updatedAt: "2026-08-09T00:00:00Z",
    }));
    const layout = buildTopologyLayout(services, dependencies);
    expect(layout.nodes).toHaveLength(100);
    expect(layout.edges).toHaveLength(99);
  });
});

describe("ServicesApi", () => {
  it("uses centralized auth/workspace headers for catalog calls", async () => {
    setApiAccessToken("access");
    setApiWorkspaceId("workspace-1");
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ services: [service("s1", "api-gateway")] }), { status: 200, headers: { "Content-Type": "application/json" } }));
    const api = new ServicesApi(new ObservaApiClient({ baseUrl: "http://backend.test" }));
    await expect(api.listCatalog()).resolves.toHaveLength(1);
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer access");
    expect((init.headers as Record<string, string>)["X-Workspace-Id"]).toBe("workspace-1");
    vi.restoreAllMocks();
    setApiAccessToken(null);
    setApiWorkspaceId(null);
  });
});
