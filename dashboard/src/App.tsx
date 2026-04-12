import { useCallback, useEffect, useRef, useState } from "react";
import { useTraces } from "./hooks/useTraces";
import { useSpans } from "./hooks/useSpans";
import { useTheme } from "./hooks/useTheme";
import { fetchTrace } from "./api/client";
import type { Trace } from "./types/api";
import { TraceList } from "./components/TraceList";
import { TraceDetail } from "./components/TraceDetail";
import { CompareView } from "./components/CompareView";
import { ResizeHandle } from "./components/ResizeHandle";
import { KeySettings } from "./components/KeySettings";

/** Create a mousedown handler that resizes a pane by dragging. */
function makeDragHandler(
  startWidth: number,
  setWidth: (w: number) => void,
  min: number,
  max: number,
) {
  return (e: React.MouseEvent) => {
    e.preventDefault();
    const startX = e.clientX;
    document.body.style.userSelect = "none";
    const onMove = (ev: MouseEvent) => {
      setWidth(Math.max(min, Math.min(max, startWidth + ev.clientX - startX)));
    };
    const onUp = () => {
      document.body.style.userSelect = "";
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  };
}

export default function App() {
  const [status, setStatus] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [offset, setOffset] = useState(0);
  const [selectedTraceId, setSelectedTraceId] = useState<string | null>(null);
  const [selectedTrace, setSelectedTrace] = useState<Trace | null>(null);
  const [selectedSpanId, setSelectedSpanId] = useState<string | null>(null);
  const [traceListWidth, setTraceListWidth] = useState(340);
  const [spanTreeWidth, setSpanTreeWidth] = useState(280);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [compareMode, setCompareMode] = useState(false);
  const [compareChecked, setCompareChecked] = useState<Set<string>>(new Set());
  const [comparePair, setComparePair] = useState<[string, string] | null>(null);
  // Snapshot the active trace/span when comparison opens so we can restore on exit
  const compareRestoreRef = useRef<{ traceId: string | null; spanId: string | null }>({
    traceId: null,
    spanId: null,
  });
  const { mode: theme, setMode: setTheme } = useTheme();

  const {
    traces,
    totalPages,
    loading,
    error,
    hasPending,
    applyPending,
    refresh,
    autoRefresh,
    setAutoRefresh,
  } = useTraces({ offset, status, q });

  const { spans, loading: spansLoading } = useSpans(selectedTraceId);

  // When a span replay completes we want to auto-select that span once the new
  // trace's spans have loaded. Store the pending span_id in a ref so the effect
  // below can fire without re-running every time spans changes.
  const pendingSpanIdRef = useRef<string | null>(null);

  useEffect(() => {
    if (pendingSpanIdRef.current && !spansLoading && spans.length > 0) {
      const target = spans.find((s) => s.span_id === pendingSpanIdRef.current);
      // If the exact replayed span id exists, select it; otherwise fall back to
      // the first llm_call span so the user lands on something useful.
      const fallback = spans.find((s) => s.kind === "llm_call") ?? spans[0];
      setSelectedSpanId((target ?? fallback).span_id);
      pendingSpanIdRef.current = null;
    }
  }, [spans, spansLoading]);

  const handleStatusChange = useCallback((v: string | null) => {
    setStatus(v);
    setOffset(0);
  }, []);

  const handleSearchChange = useCallback((v: string) => {
    setQ(v);
    setOffset(0);
  }, []);

  const handleSelectTrace = useCallback(async (id: string) => {
    setSelectedTraceId(id);
    setSelectedSpanId(null);
    try {
      const trace = await fetchTrace(id);
      setSelectedTrace(trace);
    } catch {
      // trace already in list; use list data as fallback
      const t = traces.find((tr) => tr.trace_id === id) ?? null;
      setSelectedTrace(t);
    }
  }, [traces]);

  const handleReplaySuccess = useCallback(
    (traceId: string, spanId?: string) => {
      if (spanId) pendingSpanIdRef.current = spanId;
      void handleSelectTrace(traceId);
      refresh();
    },
    [handleSelectTrace, refresh],
  );

  const handleEnterCompare = useCallback(() => {
    compareRestoreRef.current = { traceId: selectedTraceId, spanId: selectedSpanId };
    setCompareMode(true);
  }, [selectedTraceId, selectedSpanId]);

  const handleExitCompare = useCallback(() => {
    setComparePair(null);
    setCompareMode(false);
    setCompareChecked(new Set());
    const { traceId, spanId } = compareRestoreRef.current;
    if (traceId) void handleSelectTrace(traceId);
    if (spanId) setSelectedSpanId(spanId);
  }, [handleSelectTrace]);

  const handleToggleCheck = useCallback((id: string) => {
    setCompareChecked((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else if (next.size < 2) {
        next.add(id);
      } else {
        // Replace oldest selection
        next.delete(next.values().next().value!);
        next.add(id);
      }
      return next;
    });
  }, []);

  return (
    <div className="flex h-screen overflow-hidden bg-background text-text-primary">
      {/* Settings gear — fixed bottom-left */}
      <button
        onClick={() => setSettingsOpen(true)}
        title="API Key Settings"
        className="fixed bottom-3 right-3 z-40 flex h-7 w-7 items-center justify-center rounded-full bg-panel text-text-muted ring-1 ring-border hover:text-text-primary hover:ring-accent"
      >
        <svg viewBox="0 0 20 20" fill="currentColor" className="h-3.5 w-3.5">
          <path fillRule="evenodd" d="M11.49 3.17c-.38-1.56-2.6-1.56-2.98 0a1.532 1.532 0 01-2.286.948c-1.372-.836-2.942.734-2.106 2.106.54.886.061 2.042-.947 2.287-1.561.379-1.561 2.6 0 2.978a1.532 1.532 0 01.947 2.287c-.836 1.372.734 2.942 2.106 2.106a1.532 1.532 0 012.287.947c.379 1.561 2.6 1.561 2.978 0a1.533 1.533 0 012.287-.947c1.372.836 2.942-.734 2.106-2.106a1.533 1.533 0 01.947-2.287c1.561-.379 1.561-2.6 0-2.978a1.532 1.532 0 01-.947-2.287c.836-1.372-.734-2.942-2.106-2.106a1.532 1.532 0 01-2.287-.947zM10 13a3 3 0 100-6 3 3 0 000 6z" clipRule="evenodd" />
        </svg>
      </button>
      <KeySettings
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        theme={theme}
        onThemeChange={setTheme}
        onDataCleared={() => { refresh(); setSelectedTrace(null); setSelectedTraceId(null); setSelectedSpanId(null); }}
      />
      <TraceList
        width={traceListWidth}
        traces={traces}
        totalPages={totalPages}
        loading={loading}
        error={error}
        hasPending={hasPending}
        onApplyPending={applyPending}
        onRefresh={refresh}
        autoRefresh={autoRefresh}
        onAutoRefreshChange={setAutoRefresh}
        status={status}
        onStatusChange={handleStatusChange}
        onSearchChange={handleSearchChange}
        offset={offset}
        onOffsetChange={setOffset}
        selectedTraceId={selectedTraceId}
        onSelectTrace={(id) => void handleSelectTrace(id)}
        compareMode={compareMode}
        compareChecked={compareChecked}
        onEnterCompare={handleEnterCompare}
        onExitCompare={handleExitCompare}
        onToggleCheck={handleToggleCheck}
        onCompare={(pair) => setComparePair(pair)}
      />
      <ResizeHandle onMouseDown={makeDragHandler(traceListWidth, setTraceListWidth, 200, 600)} />
      {comparePair ? (
        <CompareView
          traceIds={comparePair}
          onClose={handleExitCompare}
        />
      ) : (
        <TraceDetail
          trace={selectedTrace}
          spans={spans}
          spansLoading={spansLoading}
          selectedSpanId={selectedSpanId}
          onSelectSpan={setSelectedSpanId}
          spanTreeWidth={spanTreeWidth}
          onSpanTreeDragStart={makeDragHandler(spanTreeWidth, setSpanTreeWidth, 160, 500)}
          onReplaySuccess={handleReplaySuccess}
        />
      )}
    </div>
  );
}
