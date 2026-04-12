// TypeScript types mirroring the Python Pydantic models in traceai/models.py.
// Keep in sync with the Python models.

export type SpanKind =
  | "llm_call"
  | "tool_call"
  | "memory_read"
  | "memory_write"
  | "agent_step"
  | "retrieval"
  | "embedding"
  | "custom";

export type SpanStatus = "ok" | "error" | "timeout" | "pending";

export interface ErrorDetail {
  exception_type: string;
  message: string;
  traceback: string | null;
}

export interface Span {
  span_id: string;
  trace_id: string;
  parent_span_id: string | null;
  name: string;
  kind: SpanKind;
  started_at: string;
  ended_at: string | null;
  duration_ms: number | null;
  inputs: Record<string, unknown> | null;
  outputs: Record<string, unknown> | null;
  metadata: Record<string, unknown> | null;
  status: SpanStatus;
  error: ErrorDetail | null;
  created_at: string;
}

export interface Trace {
  trace_id: string;
  name: string;
  started_at: string;
  ended_at: string | null;
  duration_ms: number | null;
  span_count: number;
  llm_call_count: number;
  total_tokens: number | null;
  total_cost_usd: number | null;
  status: SpanStatus;
  tags: Record<string, string>;
  inputs: Record<string, unknown> | null;
  outputs: Record<string, unknown> | null;
  metadata: Record<string, unknown> | null;
  created_at: string;
}

export interface Message {
  role: string;
  content: string;
}

export interface TraceReplayRequest {
  model: string;
  provider?: string;
}

export interface TraceReplayResponse {
  trace_id: string;
  spans_replayed: number;
  original_cost_usd: number | null;
  replay_cost_usd: number | null;
  original_tokens: number;
  replay_tokens: number;
}

export interface TracesResponse {
  traces: Trace[];
  total: number;
  limit: number;
  offset: number;
}
