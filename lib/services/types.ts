import type { ServiceId } from "@/lib/types";

export type ServiceHealth = "healthy" | "degraded" | "critical" | "unknown";
export type DependencyType = "http" | "queue" | "database" | "unknown";

export interface ServiceCatalogItem {
  id: string;
  workspaceId: string;
  name: ServiceId;
  displayName?: string;
  description?: string;
  environment?: string;
  version?: string;
  ownerTeam?: string;
  repositoryUrl?: string;
  runbookUrl?: string;
  tags: string[];
  lastSeenAt?: string;
  createdAt: string;
  updatedAt: string;
  health: ServiceHealth;
  recentEventCount: number;
  avgLatency?: number;
  errorRate?: number;
  throughput?: number;
  activeAlertCount: number;
  activeIncidentCount: number;
}

export interface ServiceDependency {
  id: string;
  workspaceId: string;
  sourceServiceId: string;
  targetServiceId: string;
  dependencyType: DependencyType;
  lastSeenAt?: string;
  createdAt: string;
  updatedAt: string;
  sourceServiceName?: string;
  targetServiceName?: string;
}

export interface ServiceCatalogDraft {
  name: ServiceId;
  displayName?: string;
  description?: string;
  environment?: string;
  version?: string;
  ownerTeam?: string;
  repositoryUrl?: string;
  runbookUrl?: string;
  tags: string[];
}

export interface ServiceDependencyDraft {
  sourceServiceId: string;
  targetServiceId: string;
  dependencyType: DependencyType;
}
