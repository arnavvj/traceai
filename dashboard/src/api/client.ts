import type { Span, Trace, TracesResponse } from "../types/api";

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
