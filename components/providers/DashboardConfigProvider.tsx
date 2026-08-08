"use client";

import { createContext, useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { DashboardApi } from "@/lib/api/dashboards";
import { defaultDashboard, DEFAULT_DASHBOARD_ID } from "@/lib/dashboards/defaultDashboard";
import type { DashboardConfig, DashboardWidgetConfig, WidgetDraft } from "@/lib/dashboards/types";

const SELECTED_KEY = "observa:selected-dashboard";

interface DashboardConfigState {
  dashboards: DashboardConfig[];
  activeDashboard: DashboardConfig;
  loading: boolean;
  error: string | null;
}

interface DashboardConfigActions {
  selectDashboard: (id: string) => void;
  createDashboard: (name: string) => Promise<void>;
  renameDashboard: (id: string, name: string) => Promise<void>;
  deleteDashboard: (id: string) => Promise<void>;
  addWidget: (draft: WidgetDraft) => Promise<void>;
  removeWidget: (id: string) => Promise<void>;
  moveWidget: (id: string, direction: -1 | 1) => Promise<void>;
  updateWidget: (widget: DashboardWidgetConfig) => Promise<void>;
  reloadDashboards: () => Promise<void>;
}

export const DashboardConfigContext = createContext<(DashboardConfigState & DashboardConfigActions) | null>(null);

export function DashboardConfigProvider({ children }: { children: ReactNode }) {
  const [persisted, setPersisted] = useState<DashboardConfig[]>([]);
  const [selectedId, setSelectedId] = useState(DEFAULT_DASHBOARD_ID);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const api = useMemo(() => new DashboardApi(), []);
  const dashboards = useMemo(() => [defaultDashboard, ...persisted], [persisted]);
  const activeDashboard = dashboards.find((dashboard) => dashboard.id === selectedId) ?? defaultDashboard;

  const reloadDashboards = useCallback(async () => {
    setLoading(true);
    try {
      const loaded = await api.list();
      setPersisted(loaded);
      setError(null);
      const stored = typeof window === "undefined" ? null : window.localStorage.getItem(SELECTED_KEY);
      if (stored && (stored === DEFAULT_DASHBOARD_ID || loaded.some((dashboard) => dashboard.id === stored))) setSelectedId(stored);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Dashboard API unavailable");
    } finally {
      setLoading(false);
    }
  }, [api]);

  useEffect(() => {
    const timer = window.setTimeout(() => void reloadDashboards(), 0);
    return () => window.clearTimeout(timer);
  }, [reloadDashboards]);

  const selectDashboard = useCallback((id: string) => {
    setSelectedId(id);
    window.localStorage.setItem(SELECTED_KEY, id);
  }, []);

  const createDashboard = useCallback(async (name: string) => {
    try {
      const dashboard = await api.create(name);
      setPersisted((current) => [dashboard, ...current]);
      selectDashboard(dashboard.id);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Dashboard API unavailable");
    }
  }, [api, selectDashboard]);

  const renameDashboard = useCallback(async (id: string, name: string) => {
    if (id === DEFAULT_DASHBOARD_ID) return;
    try {
      const dashboard = await api.rename(id, name);
      setPersisted((current) => current.map((item) => item.id === id ? dashboard : item));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Dashboard API unavailable");
    }
  }, [api]);

  const deleteDashboard = useCallback(async (id: string) => {
    if (id === DEFAULT_DASHBOARD_ID) return;
    try {
      await api.delete(id);
      setPersisted((current) => current.filter((dashboard) => dashboard.id !== id));
      selectDashboard(DEFAULT_DASHBOARD_ID);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Dashboard API unavailable");
    }
  }, [api, selectDashboard]);

  const updateLocalWidget = useCallback((dashboardId: string, updater: (dashboard: DashboardConfig) => DashboardConfig) => {
    setPersisted((current) => current.map((dashboard) => dashboard.id === dashboardId ? updater(dashboard) : dashboard));
  }, []);

  const addWidget = useCallback(async (draft: WidgetDraft) => {
    if (activeDashboard.system) return;
    try {
      const widget = await api.addWidget(activeDashboard, draft);
      updateLocalWidget(activeDashboard.id, (dashboard) => ({ ...dashboard, widgets: [...dashboard.widgets, widget].sort((a, b) => a.position - b.position || a.id.localeCompare(b.id)) }));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Dashboard API unavailable");
    }
  }, [activeDashboard, api, updateLocalWidget]);

  const removeWidget = useCallback(async (id: string) => {
    if (activeDashboard.system) return;
    try {
      await api.deleteWidget(activeDashboard.id, id);
      updateLocalWidget(activeDashboard.id, (dashboard) => ({ ...dashboard, widgets: dashboard.widgets.filter((widget) => widget.id !== id) }));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Dashboard API unavailable");
    }
  }, [activeDashboard, api, updateLocalWidget]);

  const updateWidget = useCallback(async (widget: DashboardWidgetConfig) => {
    if (activeDashboard.system) return;
    try {
      const updated = await api.updateWidget(activeDashboard.id, widget);
      updateLocalWidget(activeDashboard.id, (dashboard) => ({ ...dashboard, widgets: dashboard.widgets.map((item) => item.id === updated.id ? updated : item).sort((a, b) => a.position - b.position || a.id.localeCompare(b.id)) }));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Dashboard API unavailable");
    }
  }, [activeDashboard, api, updateLocalWidget]);

  const moveWidget = useCallback(async (id: string, direction: -1 | 1) => {
    if (activeDashboard.system) return;
    const ordered = [...activeDashboard.widgets].sort((a, b) => a.position - b.position || a.id.localeCompare(b.id));
    const index = ordered.findIndex((widget) => widget.id === id);
    const swapIndex = index + direction;
    if (index < 0 || swapIndex < 0 || swapIndex >= ordered.length) return;
    const first = { ...ordered[index], position: ordered[swapIndex].position };
    const second = { ...ordered[swapIndex], position: ordered[index].position };
    try {
      await Promise.all([api.updateWidget(activeDashboard.id, first), api.updateWidget(activeDashboard.id, second)]);
      updateLocalWidget(activeDashboard.id, (dashboard) => ({ ...dashboard, widgets: dashboard.widgets.map((widget) => widget.id === first.id ? first : widget.id === second.id ? second : widget).sort((a, b) => a.position - b.position || a.id.localeCompare(b.id)) }));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Dashboard API unavailable");
    }
  }, [activeDashboard, api, updateLocalWidget]);

  const value = useMemo(() => ({
    dashboards,
    activeDashboard,
    loading,
    error,
    selectDashboard,
    createDashboard,
    renameDashboard,
    deleteDashboard,
    addWidget,
    removeWidget,
    moveWidget,
    updateWidget,
    reloadDashboards,
  }), [activeDashboard, addWidget, createDashboard, dashboards, deleteDashboard, error, loading, moveWidget, reloadDashboards, removeWidget, renameDashboard, selectDashboard, updateWidget]);

  return <DashboardConfigContext.Provider value={value}>{children}</DashboardConfigContext.Provider>;
}
