import type { Span, Trace } from "../types/api";
import { TraceHeader } from "./TraceHeader";
import { SpanTree } from "./SpanTree";
import { SpanDetail } from "./SpanDetail";
import { ResizeHandle } from "./ResizeHandle";

interface Props {
  trace: Trace | null;
  spans: Span[];
  spansLoading: boolean;
  selectedSpanId: string | null;
  onSelectSpan: (id: string) => void;
  spanTreeWidth: number;
  onSpanTreeDragStart: (e: React.MouseEvent) => void;
}

export function TraceDetail({
  trace,
  spans,
  spansLoading,
  selectedSpanId,
  onSelectSpan,
  spanTreeWidth,
  onSpanTreeDragStart,
}: Props) {
  if (!trace) {
    return (
      <div className="flex flex-1 items-center justify-center text-sm text-text-muted">
        Select a trace to inspect
      </div>
    );
  }

  const selectedSpan = spans.find((s) => s.span_id === selectedSpanId) ?? null;

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <TraceHeader trace={trace} />
      {spansLoading ? (
        <div className="flex flex-1 items-center justify-center text-xs text-text-muted">
          Loading spans…
        </div>
      ) : (
        <div className="flex flex-1 overflow-hidden">
          <SpanTree
            width={spanTreeWidth}
            spans={spans}
            selectedSpanId={selectedSpanId}
            onSelectSpan={onSelectSpan}
          />
          <ResizeHandle onMouseDown={onSpanTreeDragStart} />
          <SpanDetail span={selectedSpan} />
        </div>
      )}
    </div>
  );
}
