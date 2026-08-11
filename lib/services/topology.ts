import type { ServiceCatalogItem, ServiceDependency } from "./types";

export interface TopologyNode {
  id: string;
  label: string;
  health: ServiceCatalogItem["health"];
  x: number;
  y: number;
}

export interface TopologyEdge {
  id: string;
  sourceId: string;
  targetId: string;
  dependencyType: ServiceDependency["dependencyType"];
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

export interface TopologyLayout {
  nodes: TopologyNode[];
  edges: TopologyEdge[];
}

export function buildTopologyLayout(services: readonly ServiceCatalogItem[], dependencies: readonly ServiceDependency[], width = 900, height = 360): TopologyLayout {
  const centerX = width / 2;
  const centerY = height / 2;
  const radius = Math.max(90, Math.min(width, height) * 0.36);
  const sorted = [...services].sort((left, right) => left.name.localeCompare(right.name));
  const nodes = sorted.map((service, index) => {
    const angle = sorted.length <= 1 ? 0 : (Math.PI * 2 * index) / sorted.length - Math.PI / 2;
    return {
      id: service.id,
      label: service.displayName || service.name,
      health: service.health,
      x: sorted.length <= 1 ? centerX : centerX + Math.cos(angle) * radius,
      y: sorted.length <= 1 ? centerY : centerY + Math.sin(angle) * radius,
    };
  });
  const nodeMap = new Map(nodes.map((node) => [node.id, node]));
  const sortedDependencies = [...dependencies].sort((left, right) =>
    left.sourceServiceId.localeCompare(right.sourceServiceId) ||
    left.targetServiceId.localeCompare(right.targetServiceId) ||
    left.dependencyType.localeCompare(right.dependencyType) ||
    left.id.localeCompare(right.id)
  );
  const edges = sortedDependencies.flatMap((dependency) => {
    const source = nodeMap.get(dependency.sourceServiceId);
    const target = nodeMap.get(dependency.targetServiceId);
    if (!source || !target) return [];
    return [{
      id: dependency.id,
      sourceId: source.id,
      targetId: target.id,
      dependencyType: dependency.dependencyType,
      x1: source.x,
      y1: source.y,
      x2: target.x,
      y2: target.y,
    }];
  });
  return { nodes, edges };
}

export function serviceMatchesFilters(service: ServiceCatalogItem, filters: { search: string; health: string; environment: string; tag: string }): boolean {
  const search = filters.search.trim().toLowerCase();
  const matchesSearch = !search || [service.name, service.displayName, service.ownerTeam].some((value) => value?.toLowerCase().includes(search));
  const matchesHealth = !filters.health || service.health === filters.health;
  const matchesEnvironment = !filters.environment || service.environment === filters.environment;
  const matchesTag = !filters.tag || service.tags.includes(filters.tag);
  return matchesSearch && matchesHealth && matchesEnvironment && matchesTag;
}

export function healthLabel(health: ServiceCatalogItem["health"]): string {
  if (health === "healthy") return "Healthy";
  if (health === "degraded") return "Degraded";
  if (health === "critical") return "Critical";
  return "Unknown";
}
