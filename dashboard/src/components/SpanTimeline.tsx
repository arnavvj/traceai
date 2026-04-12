import { useRef, useState } from "react";
import type { SpanKind, Span } from "../types/api";

// Bar fill colors per kind — consistent with KIND_STYLES badge palette
const KIND_COLOR: Record<SpanKind, string> = {
  llm_call:     "#818cf8", // indigo-400
  agent_step:   "#60a5fa", // blue-400
  tool_call:    "#4ade80", // green-400
  memory_read:  "#c084fc", // purple-400
  memory_write: "#c084fc",
  retrieval:    "#22d3ee", // cyan-400
  embedding:    "#facc15", // yellow-400
  custom:       "#94a3b8", // slate-400
};

function fmt(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

/** Flatten spans depth-first (mirrors SpanTree traversal order). */
function flattenDFS(
  spans: Span[],
  parentId: string | null = null,
  depth = 0,
): Array<{ span: Span; depth: number }> {
  const children = spans.filter((s) => s.parent_span_id === parentId);
  const out: Array<{ span: Span; depth: number }> = [];
  for (const span of children) {
    out.push({ span, depth });
    out.push(...flattenDFS(spans, span.span_id, depth + 1));
  }
  return out;
}

interface Tooltip {
  span: Span;
  startOffset: number;
  x: number;
  y: number;
}

interface Props {
  spans: Span[];
  selectedSpanId: string | null;
  onSelectSpan: (id: string) => void;
}

const LABEL_W = 192; // px — fixed label column width
const ROW_H   = 28;  // px — row height
const TICK_N  = 5;   // number of axis divisions

export function SpanTimeline({ spans, selectedSpanId, onSelectSpan }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [tooltip, setTooltip] = useState<Tooltip | null>(null);

  if (spans.length === 0) {
    return (
      <div className="flex flex-1 items-center justify-center text-xs text-text-muted">
        No spans to display
      </div>
    );
  }

  // ── Time bounds ──────────────────────────────────────────────────────────
  const t0 = Math.min(...spans.map((s) => new Date(s.started_at).getTime()));
  const tEnd = Math.max(
    ...spans.map((s) =>
      s.ended_at
        ? new Date(s.ended_at).getTime()
        : new Date(s.started_at).getTime() + (s.duration_ms ?? 1),
    ),
  );
  const totalMs = Math.max(tEnd - t0, 1);

  const rows = flattenDFS(spans);

  const ticks = Array.from({ length: TICK_N + 1 }, (_, i) => ({
    pct: (i / TICK_N) * 100,
    label: fmt((i / TICK_N) * totalMs),
  }));

  // ── Helpers ───────────────────────────────────────────────────────────────
  function barProps(span: Span) {
    const startMs = new Date(span.started_at).getTime() - t0;
    const durMs = span.duration_ms ?? 1;
    return {
      leftPct: (startMs / totalMs) * 100,
      widthPct: Math.max((durMs / totalMs) * 100, 0.35),
      startOffset: startMs,
    };
  }

  function handleMouseEnter(e: React.MouseEvent, span: Span, startOffset: number) {
    const rect = containerRef.current?.getBoundingClientRect();
    if (!rect) return;
    setTooltip({ span, startOffset, x: e.clientX - rect.left, y: e.clientY - rect.top });
  }

  function handleMouseMove(e: React.MouseEvent) {
    if (!tooltip) return;
    const rect = containerRef.current?.getBoundingClientRect();
    if (!rect) return;
    setTooltip((t) => t && { ...t, x: e.clientX - rect.left, y: e.clientY - rect.top });
  }

  return (
    <div ref={containerRef} className="relative flex flex-1 flex-col overflow-hidden select-none">
      {/* ── Rows ──────────────────────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto">
        {rows.map(({ span, depth }) => {
          const { leftPct, widthPct, startOffset } = barProps(span);
          const color = KIND_COLOR[span.kind];
          const selected = span.span_id === selectedSpanId;

          return (
            <div
              key={span.span_id}
              role="button"
              tabIndex={0}
              onClick={() => onSelectSpan(span.span_id)}
              onKeyDown={(e) => e.key === "Enter" && onSelectSpan(span.span_id)}
              onMouseEnter={(e) => handleMouseEnter(e, span, startOffset)}
              onMouseMove={handleMouseMove}
              onMouseLeave={() => setTooltip(null)}
              className={`flex cursor-pointer items-center border-b border-border/30 transition-colors hover:bg-panel/60 ${selected ? "bg-panel" : ""}`}
              style={{ height: ROW_H }}
            >
              {/* Label */}
              <div
                className="flex shrink-0 items-center gap-1.5 overflow-hidden pr-2 text-[11px]"
                style={{ width: LABEL_W, paddingLeft: `${8 + depth * 12}px` }}
              >
                <span
                  className="shrink-0 rounded px-1 py-0 text-[9px] font-semibold text-white"
                  style={{ backgroundColor: `${color}bb` }}
                >
                  {span.kind}
                </span>
                <span className={`truncate ${selected ? "text-text-primary font-medium" : "text-text-secondary"}`}>
                  {span.name}
                </span>
              </div>

              {/* Bar area */}
              <div className="relative flex-1" style={{ height: ROW_H }}>
                {/* Subtle vertical grid lines */}
                {ticks.slice(1, -1).map(({ pct }) => (
                  <div
                    key={pct}
                    className="absolute inset-y-0 w-px bg-border/40"
                    style={{ left: `${pct}%` }}
                  />
                ))}

                {/* Span bar */}
                <div
                  className="absolute top-1/2 -translate-y-1/2 rounded-sm transition-opacity"
                  style={{
                    left: `${leftPct}%`,
                    width: `${widthPct}%`,
                    height: 13,
                    backgroundColor: color,
                    opacity: selected ? 1 : 0.7,
                    boxShadow: selected ? `0 0 0 2px ${color}55` : "none",
                  }}
                />
              </div>

              {/* Duration */}
              <div className="w-12 shrink-0 pr-2 text-right text-[10px] text-text-muted">
                {span.duration_ms != null ? fmt(span.duration_ms) : "—"}
              </div>
            </div>
          );
        })}
      </div>

      {/* ── X-axis ────────────────────────────────────────────────────────── */}
      <div
        className="shrink-0 border-t border-border bg-background"
        style={{ paddingLeft: LABEL_W, paddingRight: 48 }}
      >
        <div className="relative h-5">
          {ticks.map(({ pct, label }) => (
            <span
              key={pct}
              className="absolute top-1 -translate-x-1/2 text-[9px] text-text-muted"
              style={{ left: `${pct}%` }}
            >
              {label}
            </span>
          ))}
        </div>
      </div>

      {/* ── Tooltip ───────────────────────────────────────────────────────── */}
      {tooltip && (
        <div
          className="pointer-events-none absolute z-50 rounded-lg border border-border bg-panel px-3 py-2 text-xs shadow-xl"
          style={{ left: tooltip.x + 14, top: tooltip.y - 10 }}
        >
          <div className="mb-1 font-semibold text-text-primary">{tooltip.span.name}</div>
          <div className="text-text-muted">{tooltip.span.kind}</div>
          <div className="mt-1 flex gap-3 text-[10px] text-text-muted">
            <span>+{fmt(tooltip.startOffset)}</span>
            <span>
              {tooltip.span.duration_ms != null ? fmt(tooltip.span.duration_ms) : "ongoing"}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
