import { useCallback, useState } from "react";
import { useTraces } from "./hooks/useTraces";
import { useSpans } from "./hooks/useSpans";
import { fetchTrace } from "./api/client";
import type { Trace } from "./types/api";
import { TraceList } from "./components/TraceList";
import { TraceDetail } from "./components/TraceDetail";
import { ResizeHandle } from "./components/ResizeHandle";

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

  const {
    traces,
    loading,
    error,
    hasPending,
    applyPending,
    refresh,
    autoRefresh,
    setAutoRefresh,
  } = useTraces({ offset, status, q });

  const { spans, loading: spansLoading } = useSpans(selectedTraceId);

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

  return (
    <div className="flex h-screen overflow-hidden bg-background text-text-primary">
      <TraceList
        width={traceListWidth}
        traces={traces}
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
      />
      <ResizeHandle onMouseDown={makeDragHandler(traceListWidth, setTraceListWidth, 200, 600)} />
      <TraceDetail
        trace={selectedTrace}
        spans={spans}
        spansLoading={spansLoading}
        selectedSpanId={selectedSpanId}
        onSelectSpan={setSelectedSpanId}
        spanTreeWidth={spanTreeWidth}
        onSpanTreeDragStart={makeDragHandler(spanTreeWidth, setSpanTreeWidth, 160, 500)}
      />
    </div>
  );
}
