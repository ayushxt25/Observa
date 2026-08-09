import { ObservaApiClient } from "./client";
import { getObservaApiUrl } from "./config";

export interface WorkspaceApiKey {
  id: string;
  workspaceId: string;
  name: string;
  keyPrefix: string;
  createdAt: string;
  lastUsedAt?: string | null;
  revokedAt?: string | null;
  expiresAt?: string | null;
}

export interface WorkspaceApiKeyCreated extends WorkspaceApiKey {
  rawKey: string;
}

interface ApiKeyListResponse {
  apiKeys: WorkspaceApiKey[];
}

export class ApiKeysApi {
  constructor(private readonly client = new ObservaApiClient({ baseUrl: getObservaApiUrl() })) {}

  async list(workspaceId: string): Promise<WorkspaceApiKey[]> {
    return (await this.client.get<ApiKeyListResponse>(`/api/v1/workspaces/${workspaceId}/api-keys`)).apiKeys;
  }

  create(workspaceId: string, name: string): Promise<WorkspaceApiKeyCreated> {
    return this.client.post<WorkspaceApiKeyCreated>(`/api/v1/workspaces/${workspaceId}/api-keys`, { name });
  }

  async revoke(workspaceId: string, keyId: string): Promise<void> {
    await this.client.delete(`/api/v1/workspaces/${workspaceId}/api-keys/${keyId}`);
  }
}
