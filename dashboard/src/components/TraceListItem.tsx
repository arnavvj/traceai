import type { Trace } from "../types/api";
import { StatusBadge } from "./StatusBadge";

function formatDuration(ms: number | null): string {
  if (ms == null) return "—";
  if (ms < 1000) return `${ms.toFixed(0)}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

function formatTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

interface Props {
  trace: Trace;
  selected: boolean;
  onClick: () => void;
}

export function TraceListItem({ trace, selected, onClick }: Props) {
  return (
    <div
      onClick={onClick}
      className={`cursor-pointer border-b border-border px-3 py-2.5 transition-colors hover:bg-panel ${selected ? "bg-panel border-l-2 border-l-accent" : ""}`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="truncate font-medium text-text-primary" title={trace.name}>
          {trace.name}
        </span>
        <StatusBadge status={trace.status} />
      </div>
      <div className="mt-1 flex items-center gap-3 text-[11px] text-text-muted">
        <span className="font-mono">{trace.trace_id.slice(0, 8)}</span>
        <span>{formatDuration(trace.duration_ms)}</span>
        <span>{trace.span_count} spans</span>
        {trace.total_tokens != null && <span>{trace.total_tokens.toLocaleString()} tok</span>}
      </div>
      <div className="mt-0.5 text-[11px] text-text-muted">{formatTime(trace.started_at)}</div>
    </div>
  );
}
