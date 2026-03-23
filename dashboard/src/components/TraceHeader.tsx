import type { Trace } from "../types/api";
import { StatusBadge } from "./StatusBadge";

function formatDuration(ms: number | null): string {
  if (ms == null) return "—";
  if (ms < 1000) return `${ms.toFixed(0)}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

function formatCost(usd: number | null): string {
  if (usd == null) return "";
  if (usd < 0.01) return `$${usd.toFixed(6)}`;
  return `$${usd.toFixed(4)}`;
}

interface Props {
  trace: Trace;
}

export function TraceHeader({ trace }: Props) {
  return (
    <div className="border-b border-border bg-panel px-4 py-3">
      <div className="flex items-center gap-3">
        <h2 className="truncate text-sm font-semibold text-text-primary">{trace.name}</h2>
        <StatusBadge status={trace.status} />
      </div>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-text-muted">
        <span>
          ID: <span className="font-mono text-text-secondary">{trace.trace_id.slice(0, 16)}</span>
        </span>
        <span>Duration: {formatDuration(trace.duration_ms)}</span>
        <span>Spans: {trace.span_count}</span>
        <span>LLM calls: {trace.llm_call_count}</span>
        {trace.total_tokens != null && (
          <span>Tokens: {trace.total_tokens.toLocaleString()}</span>
        )}
        {trace.total_cost_usd != null && (
          <span>Cost: {formatCost(trace.total_cost_usd)}</span>
        )}
        <span>
          {new Date(trace.started_at).toLocaleString(undefined, {
            month: "short",
            day: "numeric",
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
          })}
        </span>
      </div>
    </div>
  );
}
