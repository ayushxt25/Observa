export type WorkspaceRole = "owner" | "admin" | "member" | "viewer";

export interface AuthUser {
  id: string;
  email: string;
  displayName?: string;
  isActive: boolean;
}

export interface WorkspaceSummary {
  id: string;
  name: string;
  slug: string;
  role: WorkspaceRole;
}

export interface AuthResult {
  accessToken: string;
  tokenType: "bearer";
  user: AuthUser;
  workspaces: WorkspaceSummary[];
}
