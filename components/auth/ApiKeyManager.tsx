"use client";

import { useEffect, useMemo, useState } from "react";
import { ApiKeysApi, type WorkspaceApiKey, type WorkspaceApiKeyCreated } from "@/lib/api/apiKeys";
import type { WorkspaceSummary } from "@/lib/auth/types";

export function ApiKeyManager({ workspace }: { workspace: WorkspaceSummary }) {
  const api = useMemo(() => new ApiKeysApi(), []);
  const [keys, setKeys] = useState<WorkspaceApiKey[]>([]);
  const [created, setCreated] = useState<WorkspaceApiKeyCreated | null>(null);
  const [name, setName] = useState("Local generator");
  const [message, setMessage] = useState<string | null>(null);
  const canManage = workspace.role === "owner" || workspace.role === "admin";

  useEffect(() => {
    if (!canManage) return;
    let active = true;
    void api.list(workspace.id).then((items) => {
      if (active) setKeys(items);
    }).catch((error: unknown) => {
      if (active) setMessage(error instanceof Error ? error.message : "API keys unavailable");
    });
    return () => {
      active = false;
    };
  }, [api, canManage, workspace.id]);

  if (!canManage) return null;

  const create = async () => {
    try {
      const key = await api.create(workspace.id, name.trim() || "Telemetry key");
      setCreated(key);
      setKeys((current) => [key, ...current]);
      setMessage("Copy this key now. It will not be shown again.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "API key create failed");
    }
  };

  const revoke = async (key: WorkspaceApiKey) => {
    try {
      await api.revoke(workspace.id, key.id);
      setKeys((current) => current.map((item) => item.id === key.id ? { ...item, revokedAt: new Date().toISOString() } : item));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "API key revoke failed");
    }
  };

  return (
    <div className="api-key-manager">
      <label>API key name<input aria-label="API key name" value={name} onChange={(event) => setName(event.target.value)} /></label>
      <button type="button" onClick={() => void create()}>Create key</button>
      {created ? (
        <div className="api-key-once">
          <code>{created.rawKey}</code>
          <button type="button" onClick={() => void navigator.clipboard.writeText(created.rawKey)}>Copy</button>
        </div>
      ) : null}
      {message ? <span>{message}</span> : null}
      <div className="api-key-list">
        {keys.map((key) => (
          <div key={key.id} className="api-key-row">
            <span>{key.name} / {key.keyPrefix}</span>
            <small>{key.revokedAt ? "revoked" : key.lastUsedAt ? `used ${new Date(key.lastUsedAt).toLocaleTimeString()}` : "unused"}</small>
            <button type="button" disabled={Boolean(key.revokedAt)} onClick={() => void revoke(key)}>Revoke</button>
          </div>
        ))}
      </div>
    </div>
  );
}
