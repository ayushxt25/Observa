import { ObservaApiClient } from "./client";
import { getObservaApiUrl } from "./config";
import type { DependencyType, ServiceCatalogDraft, ServiceCatalogItem, ServiceDependency, ServiceDependencyDraft } from "@/lib/services/types";

interface ServiceCatalogListDto { services: ServiceCatalogItem[] }
interface ServiceDependencyListDto { dependencies: ServiceDependency[] }

function cleanText(value: string | undefined): string | undefined {
  const trimmed = value?.trim();
  return trimmed ? trimmed : undefined;
}

export function mapService(input: ServiceCatalogItem): ServiceCatalogItem {
  return {
    ...input,
    displayName: input.displayName ?? undefined,
    description: input.description ?? undefined,
    environment: input.environment ?? undefined,
    version: input.version ?? undefined,
    ownerTeam: input.ownerTeam ?? undefined,
    repositoryUrl: input.repositoryUrl ?? undefined,
    runbookUrl: input.runbookUrl ?? undefined,
    lastSeenAt: input.lastSeenAt ?? undefined,
    avgLatency: input.avgLatency ?? undefined,
    errorRate: input.errorRate ?? undefined,
    throughput: input.throughput ?? undefined,
    tags: input.tags ?? [],
  };
}

export function mapDependency(input: ServiceDependency): ServiceDependency {
  return {
    ...input,
    lastSeenAt: input.lastSeenAt ?? undefined,
    sourceServiceName: input.sourceServiceName ?? undefined,
    targetServiceName: input.targetServiceName ?? undefined,
  };
}

export function serviceDraftBody(draft: ServiceCatalogDraft): Record<string, unknown> {
  return {
    name: draft.name,
    displayName: cleanText(draft.displayName),
    description: cleanText(draft.description),
    environment: cleanText(draft.environment),
    version: cleanText(draft.version),
    ownerTeam: cleanText(draft.ownerTeam),
    repositoryUrl: cleanText(draft.repositoryUrl),
    runbookUrl: cleanText(draft.runbookUrl),
    tags: draft.tags.map((tag) => tag.trim().toLowerCase()).filter(Boolean),
  };
}

export function servicePatchBody(draft: Omit<ServiceCatalogDraft, "name">): Record<string, unknown> {
  return {
    displayName: cleanText(draft.displayName),
    description: cleanText(draft.description),
    environment: cleanText(draft.environment),
    version: cleanText(draft.version),
    ownerTeam: cleanText(draft.ownerTeam),
    repositoryUrl: cleanText(draft.repositoryUrl),
    runbookUrl: cleanText(draft.runbookUrl),
    tags: draft.tags.map((tag) => tag.trim().toLowerCase()).filter(Boolean),
  };
}

export class ServicesApi {
  constructor(private readonly client = new ObservaApiClient({ baseUrl: getObservaApiUrl() })) {}

  async listCatalog(signal?: AbortSignal): Promise<ServiceCatalogItem[]> {
    const response = await this.client.get<ServiceCatalogListDto>("/api/v1/services/catalog", { signal });
    return response.services.map(mapService);
  }

  async createService(draft: ServiceCatalogDraft, signal?: AbortSignal): Promise<ServiceCatalogItem> {
    return mapService(await this.client.post<ServiceCatalogItem>("/api/v1/services/catalog", serviceDraftBody(draft), { signal }));
  }

  async updateService(id: string, draft: Omit<ServiceCatalogDraft, "name">, signal?: AbortSignal): Promise<ServiceCatalogItem> {
    return mapService(await this.client.patch<ServiceCatalogItem>(`/api/v1/services/catalog/${id}`, servicePatchBody(draft), { signal }));
  }

  async deleteService(id: string, signal?: AbortSignal): Promise<void> {
    await this.client.delete(`/api/v1/services/catalog/${id}`, { signal });
  }

  async listDependencies(signal?: AbortSignal): Promise<ServiceDependency[]> {
    const response = await this.client.get<ServiceDependencyListDto>("/api/v1/service-dependencies", { signal });
    return response.dependencies.map(mapDependency);
  }

  async createDependency(draft: ServiceDependencyDraft, signal?: AbortSignal): Promise<ServiceDependency> {
    return mapDependency(await this.client.post<ServiceDependency>("/api/v1/service-dependencies", draft, { signal }));
  }

  async updateDependency(id: string, dependencyType: DependencyType, signal?: AbortSignal): Promise<ServiceDependency> {
    return mapDependency(await this.client.patch<ServiceDependency>(`/api/v1/service-dependencies/${id}`, { dependencyType }, { signal }));
  }

  async deleteDependency(id: string, signal?: AbortSignal): Promise<void> {
    await this.client.delete(`/api/v1/service-dependencies/${id}`, { signal });
  }
}
