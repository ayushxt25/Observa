export const DEFAULT_OBSERVA_API_URL = "http://localhost:8001";

export function getObservaApiUrl(): string {
  const configured = process.env.NEXT_PUBLIC_OBSERVA_API_URL?.trim();
  if (configured) return configured.replace(/\/$/, "");
  if (process.env.NODE_ENV === "production") return "";
  return DEFAULT_OBSERVA_API_URL;
}
