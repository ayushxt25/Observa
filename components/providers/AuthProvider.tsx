"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { AuthApi } from "@/lib/api/auth";
import { setApiAccessToken, setApiAuthFailureHandler, setApiWorkspaceId } from "@/lib/api/client";
import type { AuthUser, WorkspaceSummary } from "@/lib/auth/types";

const WORKSPACE_KEY = "observa:active-workspace";

interface AuthContextValue {
  user: AuthUser | null;
  workspaces: WorkspaceSummary[];
  activeWorkspace: WorkspaceSummary | null;
  status: "loading" | "authenticated" | "unauthenticated";
  error: string | null;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, displayName?: string) => Promise<void>;
  logout: () => Promise<void>;
  setActiveWorkspaceId: (id: string) => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const api = useMemo(() => new AuthApi(), []);
  const [user, setUser] = useState<AuthUser | null>(null);
  const [workspaces, setWorkspaces] = useState<WorkspaceSummary[]>([]);
  const [activeWorkspaceId, setActiveWorkspaceIdState] = useState<string | null>(null);
  const [status, setStatus] = useState<AuthContextValue["status"]>("loading");
  const [error, setError] = useState<string | null>(null);

  const applySession = useCallback((result: { accessToken: string; user: AuthUser; workspaces: WorkspaceSummary[] }) => {
    setApiAccessToken(result.accessToken);
    setUser(result.user);
    setWorkspaces(result.workspaces);
    const stored = window.localStorage.getItem(WORKSPACE_KEY);
    const workspace = result.workspaces.find((item) => item.id === stored) ?? result.workspaces[0] ?? null;
    setActiveWorkspaceIdState(workspace?.id ?? null);
    setApiWorkspaceId(workspace?.id ?? null);
    setStatus("authenticated");
    setError(null);
  }, []);

  const clear = useCallback(() => {
    setApiAccessToken(null);
    setApiWorkspaceId(null);
    setUser(null);
    setWorkspaces([]);
    setActiveWorkspaceIdState(null);
    setStatus("unauthenticated");
  }, []);

  useEffect(() => {
    setApiAuthFailureHandler(clear);
    void api.refresh().then(applySession).catch(() => clear());
    return () => setApiAuthFailureHandler(null);
  }, [api, applySession, clear]);

  const login = useCallback(async (email: string, password: string) => {
    try {
      applySession(await api.login(email, password));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
      throw err;
    }
  }, [api, applySession]);

  const register = useCallback(async (email: string, password: string, displayName?: string) => {
    try {
      applySession(await api.register(email, password, displayName));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Registration failed");
      throw err;
    }
  }, [api, applySession]);

  const logout = useCallback(async () => {
    await api.logout().catch(() => undefined);
    clear();
  }, [api, clear]);

  const setActiveWorkspaceId = useCallback((id: string) => {
    window.localStorage.setItem(WORKSPACE_KEY, id);
    setActiveWorkspaceIdState(id);
    setApiWorkspaceId(id);
  }, []);

  const activeWorkspace = workspaces.find((item) => item.id === activeWorkspaceId) ?? null;
  const value = useMemo(() => ({ user, workspaces, activeWorkspace, status, error, login, register, logout, setActiveWorkspaceId }), [activeWorkspace, error, login, logout, register, setActiveWorkspaceId, status, user, workspaces]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}
