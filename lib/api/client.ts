export class ObservaApiError extends Error {
  constructor(message: string, readonly status?: number, readonly cause?: unknown) {
    super(message);
    this.name = "ObservaApiError";
  }
}

export interface ApiClientOptions {
  baseUrl: string;
  timeoutMs?: number;
}

export class ObservaApiClient {
  private readonly baseUrl: string;
  private readonly timeoutMs: number;

  constructor(options: ApiClientOptions) {
    this.baseUrl = options.baseUrl.replace(/\/$/, "");
    this.timeoutMs = options.timeoutMs ?? 10_000;
  }

  async get<T>(path: string, init: RequestInit = {}): Promise<T> {
    return this.request<T>("GET", path, undefined, init);
  }

  async post<T>(path: string, body: unknown, init: RequestInit = {}): Promise<T> {
    return this.request<T>("POST", path, body, init);
  }

  async patch<T>(path: string, body: unknown, init: RequestInit = {}): Promise<T> {
    return this.request<T>("PATCH", path, body, init);
  }

  async delete(path: string, init: RequestInit = {}): Promise<void> {
    await this.request<void>("DELETE", path, undefined, init);
  }

  private async request<T>(method: string, path: string, body?: unknown, init: RequestInit = {}): Promise<T> {
    if (!this.baseUrl) throw new ObservaApiError("Remote API URL is not configured");
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), this.timeoutMs);
    const upstream = init.signal;
    const abortFromUpstream = () => controller.abort();
    if (upstream) upstream.addEventListener("abort", abortFromUpstream, { once: true });
    try {
      const response = await fetch(`${this.baseUrl}${path}`, {
        ...init,
        method,
        signal: controller.signal,
        body: body === undefined ? undefined : JSON.stringify(body),
        headers: { Accept: "application/json", ...(body === undefined ? {} : { "Content-Type": "application/json" }), ...init.headers },
      });
      if (!response.ok) throw new ObservaApiError(`Request failed with ${response.status}`, response.status);
      if (response.status === 204) return undefined as T;
      return await response.json() as T;
    } catch (error) {
      if (error instanceof ObservaApiError) throw error;
      throw new ObservaApiError(error instanceof Error ? error.message : "Network request failed", undefined, error);
    } finally {
      clearTimeout(timeout);
      if (upstream) upstream.removeEventListener("abort", abortFromUpstream);
    }
  }
}
