"use client";

import { useAuth } from "@/components/providers/AuthProvider";

export function WorkspaceSwitcher() {
  const auth = useAuth();
  if (!auth.user) return null;
  return (
    <section className="panel workspace-panel">
      <label>Workspace
        <select value={auth.activeWorkspace?.id ?? ""} onChange={(event) => auth.setActiveWorkspaceId(event.target.value)}>
          {auth.workspaces.map((workspace) => <option key={workspace.id} value={workspace.id}>{workspace.name} ({workspace.role})</option>)}
        </select>
      </label>
      <span>{auth.user.email}</span>
      <button type="button" onClick={() => void auth.logout()}>Logout</button>
    </section>
  );
}
