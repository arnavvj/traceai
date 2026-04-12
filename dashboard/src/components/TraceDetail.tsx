import { useState } from "react";
import type { Span, Trace } from "../types/api";
import { TraceHeader } from "./TraceHeader";
import { ReplayBanner } from "./ReplayBanner";
import { SpanTree } from "./SpanTree";
import { SpanDetail } from "./SpanDetail";
import { SpanTimeline } from "./SpanTimeline";
import { ResizeHandle } from "./ResizeHandle";

interface Props {
  trace: Trace | null;
  spans: Span[];
  spansLoading: boolean;
  selectedSpanId: string | null;
  onSelectSpan: (id: string) => void;
  spanTreeWidth: number;
  onSpanTreeDragStart: (e: React.MouseEvent) => void;
  onReplaySuccess: (traceId: string, spanId?: string) => void;
}

type View = "spans" | "timeline";

export function TraceDetail({
  trace,
  spans,
  spansLoading,
  selectedSpanId,
  onSelectSpan,
  spanTreeWidth,
  onSpanTreeDragStart,
  onReplaySuccess,
}: Props) {
  const [view, setView] = useState<View>("spans");

  if (!trace) {
    return (
      <div className="flex flex-1 items-center justify-center text-sm text-text-muted">
        Select a trace to inspect
      </div>
    );
  }

  const selectedSpan = spans.find((s) => s.span_id === selectedSpanId) ?? null;
  const originalModel =
    (
      spans.find((s) => s.kind === "llm_call")
        ?.metadata as { "gen_ai.request.model"?: string } | null
    )?.["gen_ai.request.model"] ?? undefined;

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <TraceHeader trace={trace} originalModel={originalModel} onReplaySuccess={onReplaySuccess} />
      <ReplayBanner trace={trace} onSelectTrace={onReplaySuccess} />

      {/* View toggle tab bar */}
      {!spansLoading && spans.length > 0 && (
        <div className="flex shrink-0 items-center gap-0.5 border-b border-border bg-background px-3 py-1">
          {(["spans", "timeline"] as const).map((v) => (
            <button
              key={v}
              onClick={() => setView(v)}
              className={`rounded px-2.5 py-0.5 text-[11px] font-medium capitalize transition-colors ${
                view === v
                  ? "bg-accent/15 text-accent"
                  : "text-text-muted hover:text-text-secondary"
              }`}
            >
              {v}
            </button>
          ))}
        </div>
      )}

      {spansLoading ? (
        <div className="flex flex-1 items-center justify-center text-xs text-text-muted">
          Loading spans…
        </div>
      ) : view === "timeline" ? (
        <SpanTimeline
          spans={spans}
          selectedSpanId={selectedSpanId}
          onSelectSpan={onSelectSpan}
        />
      ) : (
        <div className="flex flex-1 overflow-hidden">
          <SpanTree
            width={spanTreeWidth}
            spans={spans}
            selectedSpanId={selectedSpanId}
            onSelectSpan={onSelectSpan}
          />
          <ResizeHandle onMouseDown={onSpanTreeDragStart} />
          <SpanDetail span={selectedSpan} onReplaySuccess={onReplaySuccess} />
        </div>
      )}
    </div>
  );
}
