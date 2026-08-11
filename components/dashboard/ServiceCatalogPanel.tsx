"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type WheelEvent } from "react";
import { ServicesApi } from "@/lib/api/services";
import { useAuth } from "@/components/providers/AuthProvider";
import { buildTopologyLayout, healthLabel, serviceMatchesFilters } from "@/lib/services/topology";
import type { DependencyType, ServiceCatalogDraft, ServiceCatalogItem, ServiceDependency, ServiceDependencyDraft, ServiceHealth } from "@/lib/services/types";

const initialServiceDraft: ServiceCatalogDraft = {
  name: "api-gateway",
  displayName: "",
  description: "",
  environment: "",
  version: "",
  ownerTeam: "",
  repositoryUrl: "",
  runbookUrl: "",
  tags: [],
};

const dependencyTypes: DependencyType[] = ["http", "queue", "database", "unknown"];
const healthStates: Array<ServiceHealth | ""> = ["", "healthy", "degraded", "critical", "unknown"];

function formatDate(value?: string): string {
  return value ? new Date(value).toLocaleString() : "Not seen";
}

function formatMetric(value?: number, suffix = ""): string {
  return value === undefined ? "--" : `${value.toFixed(2)}${suffix}`;
}

function tagsFromInput(value: string): string[] {
  return value.split(",").map((tag) => tag.trim().toLowerCase()).filter(Boolean);
}

export function ServiceCatalogPanel() {
  const api = useMemo(() => new ServicesApi(), []);
  const auth = useAuth();
  const workspaceId = auth.activeWorkspace?.id;
  const canEdit = auth.activeWorkspace?.role !== "viewer";
  const [services, setServices] = useState<ServiceCatalogItem[]>([]);
  const [dependencies, setDependencies] = useState<ServiceDependency[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState<ServiceCatalogDraft>(initialServiceDraft);
  const [dependencyDraft, setDependencyDraft] = useState<ServiceDependencyDraft>({ sourceServiceId: "", targetServiceId: "", dependencyType: "http" });
  const [filters, setFilters] = useState({ search: "", health: "", environment: "", tag: "" });
  const [message, setMessage] = useState<string | null>(null);
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);
  const [incidentImpact, setIncidentImpact] = useState<{ rootName: string | null; affectedNames: string[] }>({ rootName: null, affectedNames: [] });
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const dragRef = useRef<{ x: number; y: number; panX: number; panY: number } | null>(null);
  const latestRequestRef = useRef(0);

  const reload = useCallback(async (signal?: AbortSignal) => {
    const requestId = latestRequestRef.current + 1;
    latestRequestRef.current = requestId;
    try {
      const [catalog, edges] = await Promise.all([api.listCatalog(signal), api.listDependencies(signal)]);
      if (signal?.aborted || requestId !== latestRequestRef.current) return;
      setServices(catalog);
      setDependencies(edges);
      setSelectedId((current) => current && catalog.some((service) => service.id === current) ? current : catalog[0]?.id ?? null);
      setDependencyDraft((current) => ({
        sourceServiceId: current.sourceServiceId || catalog[0]?.id || "",
        targetServiceId: current.targetServiceId || catalog[1]?.id || catalog[0]?.id || "",
        dependencyType: current.dependencyType,
      }));
      setMessage(null);
    } catch (error) {
      if (signal?.aborted || requestId !== latestRequestRef.current) return;
      setServices([]);
      setDependencies([]);
      setMessage(error instanceof Error ? error.message : "Service catalog unavailable");
    }
  }, [api]);

  useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      setServices([]);
      setDependencies([]);
      setSelectedId(null);
      setEditingId(null);
      void reload(controller.signal);
    }, 0);
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [workspaceId, reload]);

  useEffect(() => {
    const onImpact = (event: Event) => {
      const detail = (event as CustomEvent<{ rootName?: string | null; affectedNames?: string[] }>).detail;
      setIncidentImpact({ rootName: detail?.rootName ?? null, affectedNames: detail?.affectedNames ?? [] });
    };
    window.addEventListener("observa:incident-impact", onImpact);
    return () => window.removeEventListener("observa:incident-impact", onImpact);
  }, []);

  const filteredServices = useMemo(() => services.filter((service) => serviceMatchesFilters(service, filters)), [filters, services]);
  const environments = useMemo(() => Array.from(new Set(services.map((service) => service.environment).filter(Boolean) as string[])).sort(), [services]);
  const tags = useMemo(() => Array.from(new Set(services.flatMap((service) => service.tags))).sort(), [services]);
  const selected = services.find((service) => service.id === selectedId) ?? null;
  const visibleIds = useMemo(() => new Set(filteredServices.map((service) => service.id)), [filteredServices]);
  const visibleDependencies = useMemo(() => dependencies.filter((dependency) => visibleIds.has(dependency.sourceServiceId) && visibleIds.has(dependency.targetServiceId)), [dependencies, visibleIds]);
  const topology = useMemo(() => buildTopologyLayout(filteredServices, visibleDependencies), [filteredServices, visibleDependencies]);
  const impactedServiceNames = useMemo(() => new Set(incidentImpact.affectedNames), [incidentImpact]);
  const serviceNameById = useMemo(() => new Map(services.map((service) => [service.id, service.name])), [services]);

  const impactClass = (name: string | undefined): string => {
    if (!name) return "";
    if (incidentImpact.rootName === name) return "impact-root";
    if (impactedServiceNames.has(name)) return "impact-affected";
    return "";
  };

  const saveService = async () => {
    if (!draft.name.trim()) {
      setMessage("Service name is required");
      return;
    }
    try {
      if (editingId) await api.updateService(editingId, draft);
      else await api.createService(draft);
      setEditingId(null);
      setDraft(initialServiceDraft);
      await reload();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Service save failed");
    }
  };

  const editService = (service: ServiceCatalogItem) => {
    setEditingId(service.id);
    setDraft({
      name: service.name,
      displayName: service.displayName ?? "",
      description: service.description ?? "",
      environment: service.environment ?? "",
      version: service.version ?? "",
      ownerTeam: service.ownerTeam ?? "",
      repositoryUrl: service.repositoryUrl ?? "",
      runbookUrl: service.runbookUrl ?? "",
      tags: service.tags,
    });
  };

  const saveDependency = async () => {
    if (!dependencyDraft.sourceServiceId || !dependencyDraft.targetServiceId || dependencyDraft.sourceServiceId === dependencyDraft.targetServiceId) {
      setMessage("Dependency needs two different services");
      return;
    }
    try {
      await api.createDependency(dependencyDraft);
      await reload();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Dependency save failed");
    }
  };

  const onWheel = (event: WheelEvent<SVGSVGElement>) => {
    event.preventDefault();
    setZoom((current) => Math.min(2.4, Math.max(0.55, current + (event.deltaY < 0 ? 0.1 : -0.1))));
  };

  return (
    <section className="panel service-catalog-panel">
      <div className="section-heading">
        <h2>Service catalog</h2>
        <span>{message ?? `${filteredServices.length}/${services.length} services / ${dependencies.length} dependencies`}</span>
      </div>
      <div className="service-controls">
        <label>Search<input aria-label="Search services" value={filters.search} onChange={(event) => setFilters((current) => ({ ...current, search: event.target.value }))} /></label>
        <label>Health<select aria-label="Filter service health" value={filters.health} onChange={(event) => setFilters((current) => ({ ...current, health: event.target.value }))}>{healthStates.map((state) => <option key={state || "all"} value={state}>{state || "all"}</option>)}</select></label>
        <label>Environment<select aria-label="Filter service environment" value={filters.environment} onChange={(event) => setFilters((current) => ({ ...current, environment: event.target.value }))}><option value="">all</option>{environments.map((item) => <option key={item} value={item}>{item}</option>)}</select></label>
        <label>Tag<select aria-label="Filter service tag" value={filters.tag} onChange={(event) => setFilters((current) => ({ ...current, tag: event.target.value }))}><option value="">all</option>{tags.map((tag) => <option key={tag} value={tag}>{tag}</option>)}</select></label>
        <button type="button" onClick={() => void reload()}>Refresh</button>
      </div>
      <div className="service-layout">
        <div className="service-list">
          {filteredServices.length === 0 ? <p>No services observed yet.</p> : filteredServices.map((service) => (
            <button type="button" className={`service-row health-${service.health} ${selectedId === service.id ? "active" : ""} ${impactClass(service.name)}`} key={service.id} onClick={() => setSelectedId(service.id)}>
              <strong>{service.displayName || service.name}</strong>
              <span>{healthLabel(service.health)} / {service.environment || "no env"} / {service.recentEventCount} events</span>
              <span>{formatMetric(service.avgLatency, " ms")} latency / {formatMetric(service.errorRate, "%")} errors</span>
            </button>
          ))}
        </div>
        <div className="service-detail">
          {selected ? (
            <>
              <div className={`service-detail-head health-${selected.health}`}>
                <h3>{selected.displayName || selected.name}</h3>
                <span>{healthLabel(selected.health)} / last seen {formatDate(selected.lastSeenAt)}</span>
              </div>
              <div className="service-stats">
                <span><strong>{formatMetric(selected.avgLatency, " ms")}</strong>Latency</span>
                <span><strong>{formatMetric(selected.errorRate, "%")}</strong>Error rate</span>
                <span><strong>{formatMetric(selected.throughput)}</strong>Throughput</span>
                <span><strong>{selected.activeIncidentCount}</strong>Active incidents</span>
              </div>
              <p>{selected.description || "No service description yet."}</p>
              <span className="service-tags">{selected.tags.length ? selected.tags.join(", ") : "No tags"}</span>
              <div className="service-detail-actions">
                <button type="button" disabled={!canEdit} onClick={() => editService(selected)}>Edit metadata</button>
                <button type="button" disabled={!canEdit} className="danger" onClick={() => void api.deleteService(selected.id).then(() => reload()).catch((error: unknown) => setMessage(error instanceof Error ? error.message : "Service delete failed"))}>Delete metadata</button>
              </div>
            </>
          ) : <p>Select a service to view metadata and health.</p>}
        </div>
      </div>
      <div className="service-editor">
        <label>Canonical name<input aria-label="Service canonical name" disabled={Boolean(editingId)} value={draft.name} onChange={(event) => setDraft((current) => ({ ...current, name: event.target.value }))} /></label>
        <label>Display name<input aria-label="Service display name" value={draft.displayName ?? ""} onChange={(event) => setDraft((current) => ({ ...current, displayName: event.target.value }))} /></label>
        <label>Environment<input aria-label="Service environment" value={draft.environment ?? ""} onChange={(event) => setDraft((current) => ({ ...current, environment: event.target.value }))} /></label>
        <label>Version<input aria-label="Service version" value={draft.version ?? ""} onChange={(event) => setDraft((current) => ({ ...current, version: event.target.value }))} /></label>
        <label>Owner team<input aria-label="Service owner team" value={draft.ownerTeam ?? ""} onChange={(event) => setDraft((current) => ({ ...current, ownerTeam: event.target.value }))} /></label>
        <label>Tags<input aria-label="Service tags" value={draft.tags.join(", ")} onChange={(event) => setDraft((current) => ({ ...current, tags: tagsFromInput(event.target.value) }))} /></label>
        <label>Description<input aria-label="Service description" value={draft.description ?? ""} onChange={(event) => setDraft((current) => ({ ...current, description: event.target.value }))} /></label>
        <button type="button" disabled={!canEdit} onClick={() => void saveService()}>{editingId ? "Save service" : "Create service"}</button>
      </div>
      <div className="service-map-shell">
        <div className="section-heading">
          <h3>Topology</h3>
          <span>{hoveredNode ? topology.nodes.find((node) => node.id === hoveredNode)?.label : "SVG service map"}</span>
        </div>
        <svg
          className="service-map"
          viewBox="0 0 900 360"
          role="img"
          aria-label="Service topology map"
          onWheel={onWheel}
          onPointerDown={(event) => { dragRef.current = { x: event.clientX, y: event.clientY, panX: pan.x, panY: pan.y }; event.currentTarget.setPointerCapture(event.pointerId); }}
          onPointerMove={(event) => {
            if (!dragRef.current) return;
            setPan({ x: dragRef.current.panX + event.clientX - dragRef.current.x, y: dragRef.current.panY + event.clientY - dragRef.current.y });
          }}
          onPointerUp={() => { dragRef.current = null; }}
        >
          <title>Service topology</title>
          <desc>Workspace service dependency graph with health encoded on each node.</desc>
          <g transform={`translate(${pan.x} ${pan.y}) scale(${zoom})`}>
            {topology.edges.map((edge) => (
              <g key={edge.id}>
                <line x1={edge.x1} y1={edge.y1} x2={edge.x2} y2={edge.y2} className="service-edge" />
                <text x={(edge.x1 + edge.x2) / 2} y={(edge.y1 + edge.y2) / 2 - 5} className="service-edge-label">{edge.dependencyType}</text>
              </g>
            ))}
            {topology.nodes.map((node) => (
              <g key={node.id} className={`service-node health-${node.health} ${selectedId === node.id ? "active" : ""} ${impactClass(serviceNameById.get(node.id))}`} transform={`translate(${node.x} ${node.y})`} onMouseEnter={() => setHoveredNode(node.id)} onMouseLeave={() => setHoveredNode(null)} onClick={() => setSelectedId(node.id)}>
                <circle r="26" />
                <text y="44">{node.label}</text>
              </g>
            ))}
          </g>
        </svg>
        <div className="service-editor compact">
          <label>Source<select aria-label="Dependency source" value={dependencyDraft.sourceServiceId} onChange={(event) => setDependencyDraft((current) => ({ ...current, sourceServiceId: event.target.value }))}>{services.map((service) => <option key={service.id} value={service.id}>{service.displayName || service.name}</option>)}</select></label>
          <label>Target<select aria-label="Dependency target" value={dependencyDraft.targetServiceId} onChange={(event) => setDependencyDraft((current) => ({ ...current, targetServiceId: event.target.value }))}>{services.map((service) => <option key={service.id} value={service.id}>{service.displayName || service.name}</option>)}</select></label>
          <label>Type<select aria-label="Dependency type" value={dependencyDraft.dependencyType} onChange={(event) => setDependencyDraft((current) => ({ ...current, dependencyType: event.target.value as DependencyType }))}>{dependencyTypes.map((type) => <option key={type} value={type}>{type}</option>)}</select></label>
          <button type="button" disabled={!canEdit || services.length < 2} onClick={() => void saveDependency()}>Add dependency</button>
        </div>
        <div className="service-dependency-list">
          {dependencies.length === 0 ? <p>No dependencies configured.</p> : dependencies.map((dependency) => (
            <article className="incident-row" key={dependency.id}>
              <strong>{dependency.sourceServiceName ?? dependency.sourceServiceId} {"->"} {dependency.targetServiceName ?? dependency.targetServiceId}</strong>
              <span>{dependency.dependencyType}</span>
              <button type="button" disabled={!canEdit} className="danger" onClick={() => void api.deleteDependency(dependency.id).then(() => reload()).catch((error: unknown) => setMessage(error instanceof Error ? error.message : "Dependency delete failed"))}>Delete</button>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
