import type { Trace } from "../types/api";
import { FilterBar } from "./FilterBar";
import { TraceListItem } from "./TraceListItem";
import { PAGE_SIZE } from "../hooks/useTraces";

interface Props {
  width: number;
  traces: Trace[];
  loading: boolean;
  error: string | null;
  hasPending: boolean;
  onApplyPending: () => void;
  onRefresh: () => void;
  autoRefresh: boolean;
  onAutoRefreshChange: (v: boolean) => void;
  status: string | null;
  onStatusChange: (v: string | null) => void;
  onSearchChange: (v: string) => void;
  offset: number;
  onOffsetChange: (v: number) => void;
  selectedTraceId: string | null;
  onSelectTrace: (id: string) => void;
}

export function TraceList({
  width,
  traces,
  loading,
  error,
  hasPending,
  onApplyPending,
  onRefresh,
  autoRefresh,
  onAutoRefreshChange,
  status,
  onStatusChange,
  onSearchChange,
  offset,
  onOffsetChange,
  selectedTraceId,
  onSelectTrace,
}: Props) {
  const page = Math.floor(offset / PAGE_SIZE) + 1;
  const hasNext = traces.length === PAGE_SIZE;
  const hasPrev = offset > 0;

  return (
    <div className="flex h-full flex-shrink-0 flex-col border-r border-border bg-sidebar" style={{ width }}>
      <div className="flex items-center justify-between border-b border-border px-3 py-2">
        <span className="text-sm font-semibold text-text-primary">TraceAI</span>
        <span className="text-xs text-text-muted">{traces.length} traces</span>
      </div>

      <FilterBar
        status={status}
        onStatusChange={onStatusChange}
        onSearchChange={onSearchChange}
        onRefresh={onRefresh}
        autoRefresh={autoRefresh}
        onAutoRefreshChange={onAutoRefreshChange}
      />

      {hasPending && (
        <button
          onClick={onApplyPending}
          className="border-b border-green-600 bg-green-600 py-2 text-center text-xs font-semibold text-white hover:bg-green-500"
        >
          New traces available — click to refresh
        </button>
      )}

      {error && (
        <div className="border-b border-red-800 bg-red-900/20 px-3 py-2 text-xs text-red-400">
          {error}
        </div>
      )}

      <div className="flex-1 overflow-y-auto">
        {loading ? (
          <div className="flex h-24 items-center justify-center text-xs text-text-muted">
            Loading…
          </div>
        ) : traces.length === 0 ? (
          <div className="flex h-24 items-center justify-center text-xs text-text-muted">
            No traces found
          </div>
        ) : (
          traces.map((t) => (
            <TraceListItem
              key={t.trace_id}
              trace={t}
              selected={t.trace_id === selectedTraceId}
              onClick={() => onSelectTrace(t.trace_id)}
            />
          ))
        )}
      </div>

      <div className="flex items-center justify-between border-t border-border px-3 py-2">
        <button
          disabled={!hasPrev}
          onClick={() => onOffsetChange(Math.max(0, offset - PAGE_SIZE))}
          className="rounded px-2 py-1 text-xs text-text-secondary disabled:opacity-40 hover:bg-border"
        >
          ← Prev
        </button>
        <span className="text-xs text-text-muted">Page {page}</span>
        <button
          disabled={!hasNext}
          onClick={() => onOffsetChange(offset + PAGE_SIZE)}
          className="rounded px-2 py-1 text-xs text-text-secondary disabled:opacity-40 hover:bg-border"
        >
          Next →
        </button>
      </div>
    </div>
  );
}
