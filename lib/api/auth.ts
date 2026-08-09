import { ObservaApiClient } from "./client";
import { getObservaApiUrl } from "./config";
import type { AuthResult, WorkspaceSummary } from "@/lib/auth/types";

interface WorkspaceListDto { workspaces: WorkspaceSummary[] }

export class AuthApi {
  constructor(private readonly client = new ObservaApiClient({ baseUrl: getObservaApiUrl() })) {}

  register(email: string, password: string, displayName?: string): Promise<AuthResult> {
    return this.client.post<AuthResult>("/api/v1/auth/register", { email, password, displayName });
  }

  login(email: string, password: string): Promise<AuthResult> {
    return this.client.post<AuthResult>("/api/v1/auth/login", { email, password });
  }

  refresh(): Promise<AuthResult> {
    return this.client.post<AuthResult>("/api/v1/auth/refresh", {});
  }

  me(): Promise<AuthResult> {
    return this.client.get<AuthResult>("/api/v1/auth/me");
  }

  async logout(): Promise<void> {
    await this.client.post<void>("/api/v1/auth/logout", {});
  }

  async listWorkspaces(): Promise<WorkspaceSummary[]> {
    return (await this.client.get<WorkspaceListDto>("/api/v1/workspaces")).workspaces;
  }

  async createWorkspace(name: string): Promise<WorkspaceSummary> {
    return this.client.post<WorkspaceSummary>("/api/v1/workspaces", { name });
  }
}
