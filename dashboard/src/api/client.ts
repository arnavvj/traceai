import type { Message, Span, Trace, TraceReplayRequest, TraceReplayResponse, TracesResponse } from "../types/api";

// Relative base — works both in production (same origin as FastAPI)
// and dev (Vite proxies /api → localhost:8765).
const BASE = "";

async function apiFetch<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) {
    throw new Error(`API ${path} returned ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export interface ListTracesParams {
  limit?: number;
  offset?: number;
  status?: string | null;
  q?: string | null;
}

export async function fetchTraces(params: ListTracesParams = {}): Promise<TracesResponse> {
  const qs = new URLSearchParams();
  if (params.limit != null) qs.set("limit", String(params.limit));
  if (params.offset != null) qs.set("offset", String(params.offset));
  if (params.status) qs.set("status", params.status);
  if (params.q) qs.set("q", params.q);
  const query = qs.toString() ? `?${qs.toString()}` : "";
  return apiFetch<TracesResponse>(`/api/traces${query}`);
}

export async function fetchTrace(traceId: string): Promise<Trace> {
  const data = await apiFetch<{ trace: Trace }>(`/api/traces/${traceId}`);
  return data.trace;
}

export async function fetchSpans(traceId: string): Promise<Span[]> {
  const data = await apiFetch<{ spans: Span[] }>(`/api/traces/${traceId}/spans`);
  return data.spans;
}

export interface ReplayRequest {
  messages?: Message[];
  model?: string;
  provider?: string;
}

export interface ReplayResponse {
  trace_id: string;
  span_id: string;
}

async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const b = await res.json().catch(() => ({}));
    throw new Error((b as { detail?: string }).detail ?? `POST ${path} failed: ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export async function replaySpan(spanId: string, req: ReplayRequest = {}): Promise<ReplayResponse> {
  return apiPost<ReplayResponse>(`/api/spans/${spanId}/replay`, req);
}

export async function replayTrace(
  traceId: string,
  req: TraceReplayRequest,
): Promise<TraceReplayResponse> {
  return apiPost<TraceReplayResponse>(`/api/traces/${traceId}/replay`, req);
}

// --- Key management ---

export interface KeyStatus {
  provider: string;
  is_set: boolean;
  source: string; // "env" | "config" | "none"
}

export async function fetchKeys(): Promise<KeyStatus[]> {
  return apiFetch<KeyStatus[]>("/api/keys");
}

export async function setKey(provider: string, key: string): Promise<void> {
  await apiPost<unknown>("/api/keys", { provider, key });
}

export async function clearAllTraces(): Promise<{ deleted: number }> {
  const res = await fetch(`${BASE}/api/traces`, { method: "DELETE" });
  if (!res.ok) throw new Error(`Clear failed: ${res.status}`);
  return res.json() as Promise<{ deleted: number }>;
}

export async function deleteKey(provider: string): Promise<void> {
  const res = await fetch(`${BASE}/api/keys/${encodeURIComponent(provider)}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`Delete key failed: ${res.status}`);
}

export type ModelMap = Record<string, string[]>;

export async function fetchModels(): Promise<ModelMap> {
  return apiFetch<ModelMap>("/api/models");
}

export type ProviderMap = Record<string, boolean>;

export async function fetchProviders(): Promise<ProviderMap> {
  return apiFetch<ProviderMap>("/api/providers");
}
