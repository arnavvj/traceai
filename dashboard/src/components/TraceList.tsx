import { useMemo } from "react";
import type { Trace } from "../types/api";
import { FilterBar } from "./FilterBar";
import { TraceListItem } from "./TraceListItem";
import { PAGE_SIZE } from "../hooks/useTraces";
import { replayFamily } from "../utils/compare";

interface Props {
  width: number;
  traces: Trace[];
  totalPages: number;
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
  compareMode: boolean;
  compareChecked: Set<string>;
  onEnterCompare: () => void;
  onExitCompare: () => void;
  onToggleCheck: (id: string) => void;
  onCompare: (pair: [string, string]) => void;
}

interface TreeNode {
  trace: Trace;
  depth: number;
  isLast: boolean;
}

/**
 * Build a flat ordered list for rendering, with depth=0 (root) or depth=1 (child).
 *
 * Rules:
 * 1. Trace replays (tags.replay_model, no tags.replay_span) → always root.
 * 2. Span replays (tags.replay_span present) → child of their DIRECT parent
 *    (tags.replay_of_trace), IF that parent is visible on this page AND the
 *    parent is itself a root (depth 0). This caps display depth at 1.
 * 3. If the direct parent is a depth-1 child (span replay of a span replay),
 *    the new replay becomes a root — no depth-2 nesting.
 * 4. Orphans (parent not on this page) → roots.
 */
function buildTree(traces: Trace[]): TreeNode[] {
  const byId = new Map(traces.map((t) => [t.trace_id, t]));

  const roots: Trace[] = [];
  const childrenByParent = new Map<string, Trace[]>();

  for (const t of traces) {
    const isSpanReplay = Boolean(t.tags?.replay_span);
    if (!isSpanReplay) {
      roots.push(t);
      continue;
    }

    const parentId = t.tags?.replay_of_trace as string | undefined;
    const parent = parentId ? byId.get(parentId) : undefined;
    // Only nest if the direct parent is on this page AND is itself a root (not a span-replay)
    const parentIsRoot = parent !== undefined && !Boolean(parent.tags?.replay_span);

    if (parentIsRoot && parentId) {
      const list = childrenByParent.get(parentId) ?? [];
      list.push(t);
      childrenByParent.set(parentId, list);
    } else {
      roots.push(t);
    }
  }

  const nodes: TreeNode[] = [];
  for (const root of roots) {
    nodes.push({ trace: root, depth: 0, isLast: false });
    const children = childrenByParent.get(root.trace_id) ?? [];
    children.forEach((child, i) => {
      nodes.push({ trace: child, depth: 1, isLast: i === children.length - 1 });
    });
  }

  return nodes;
}

export function TraceList({
  width,
  traces,
  totalPages,
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
  compareMode,
  compareChecked,
  onEnterCompare,
  onExitCompare,
  onToggleCheck,
  onCompare,
}: Props) {
  const page = Math.floor(offset / PAGE_SIZE) + 1;
  const hasNext = page < totalPages;
  const hasPrev = offset > 0;

  const treeNodes = buildTree(traces);

  const checkedArr = Array.from(compareChecked);

  // Once the first trace is checked, only allow selecting traces from the same
  // replay family.  Unrelated traces are dimmed/disabled.
  const allowedFamily = useMemo(() => {
    if (!compareMode || checkedArr.length === 0) return null;
    const firstTrace = traces.find((t) => t.trace_id === checkedArr[0]);
    return firstTrace ? replayFamily(firstTrace) : null;
  }, [compareMode, checkedArr, traces]);

  return (
    <div className="flex h-full flex-shrink-0 flex-col border-r border-border bg-sidebar" style={{ width }}>
      <div className="flex items-center justify-between border-b border-border px-3 py-2">
        <span className="text-sm font-semibold text-text-primary">TraceAI</span>
        <div className="flex items-center gap-2">
          {compareMode && checkedArr.length === 2 && (
            <button
              onClick={() => onCompare(checkedArr as [string, string])}
              className="rounded bg-accent px-2 py-0.5 text-[10px] font-semibold text-white hover:bg-accent/80"
            >
              Compare
            </button>
          )}
          <button
            onClick={compareMode ? onExitCompare : onEnterCompare}
            className={`rounded px-2 py-0.5 text-[10px] transition-colors ${
              compareMode
                ? "bg-accent/15 font-semibold text-accent"
                : "text-text-muted hover:text-text-secondary"
            }`}
          >
            {compareMode ? `✕ Cancel (${checkedArr.length}/2)` : "⇄ Compare"}
          </button>
        </div>
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
        <div className="border-b border-red-300 bg-red-50 px-3 py-2 text-xs text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-400">
          {error}
        </div>
      )}

      <div className="flex-1 overflow-y-auto">
        {loading ? (
          <div className="flex h-24 items-center justify-center text-xs text-text-muted">
            Loading…
          </div>
        ) : treeNodes.length === 0 ? (
          <div className="flex h-24 items-center justify-center text-xs text-text-muted">
            No traces found
          </div>
        ) : (
          treeNodes.map(({ trace, depth, isLast }) => {
            const isDisabled =
              compareMode &&
              allowedFamily != null &&
              !compareChecked.has(trace.trace_id) &&
              replayFamily(trace) !== allowedFamily;
            return (
              <TraceListItem
                key={trace.trace_id}
                trace={trace}
                selected={trace.trace_id === selectedTraceId}
                onClick={() => onSelectTrace(trace.trace_id)}
                depth={depth}
                isLast={isLast}
                compareMode={compareMode}
                checked={compareChecked.has(trace.trace_id)}
                onCheck={() => onToggleCheck(trace.trace_id)}
                disabled={isDisabled}
              />
            );
          })
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
        <span className="text-xs text-text-muted">Page {page}/{totalPages}</span>
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
