import type { Span, SpanKind } from "../types/api";

const KIND_STYLES: Record<SpanKind, string> = {
  llm_call: "bg-indigo-900/50 text-indigo-300 border border-indigo-800",
  tool_call: "bg-green-900/50 text-green-300 border border-green-800",
  memory_read: "bg-purple-900/50 text-purple-300 border border-purple-800",
  memory_write: "bg-purple-900/50 text-purple-300 border border-purple-800",
  agent_step: "bg-blue-900/50 text-blue-300 border border-blue-800",
  retrieval: "bg-cyan-900/50 text-cyan-300 border border-cyan-800",
  embedding: "bg-yellow-900/50 text-yellow-300 border border-yellow-800",
  custom: "bg-gray-800/50 text-gray-300 border border-gray-700",
};

function formatDuration(ms: number | null): string {
  if (ms == null) return "";
  if (ms < 1000) return `${ms.toFixed(0)}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

interface SpanNodeProps {
  span: Span;
  children: Span[];
  allSpans: Span[];
  depth: number;
  selectedSpanId: string | null;
  onSelect: (id: string) => void;
}

function SpanNode({ span, children, allSpans, depth, selectedSpanId, onSelect }: SpanNodeProps) {
  return (
    <div>
      <div
        onClick={() => onSelect(span.span_id)}
        className={`flex cursor-pointer items-center gap-2 border-b border-border py-1.5 pr-3 text-xs transition-colors hover:bg-panel ${selectedSpanId === span.span_id ? "bg-panel border-l-2 border-l-accent" : ""}`}
        style={{ paddingLeft: `${12 + depth * 16}px` }}
      >
        <span className={`shrink-0 rounded px-1 py-0.5 text-[10px] font-medium ${KIND_STYLES[span.kind]}`}>
          {span.kind}
        </span>
        <span className="min-w-0 truncate text-text-primary">{span.name}</span>
        <span className="ml-auto shrink-0 text-text-muted">{formatDuration(span.duration_ms)}</span>
      </div>
      {children.map((child) => (
        <SpanNode
          key={child.span_id}
          span={child}
          children={allSpans.filter((s) => s.parent_span_id === child.span_id)}
          allSpans={allSpans}
          depth={depth + 1}
          selectedSpanId={selectedSpanId}
          onSelect={onSelect}
        />
      ))}
    </div>
  );
}

interface Props {
  width: number;
  spans: Span[];
  selectedSpanId: string | null;
  onSelectSpan: (id: string) => void;
}

export function SpanTree({ width, spans, selectedSpanId, onSelectSpan }: Props) {
  const roots = spans.filter((s) => !s.parent_span_id);

  return (
    <div className="shrink-0 overflow-y-auto border-r border-border" style={{ width }}>
      <div className="border-b border-border px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wide text-text-muted">
        Spans ({spans.length})
      </div>
      {roots.map((span) => (
        <SpanNode
          key={span.span_id}
          span={span}
          children={spans.filter((s) => s.parent_span_id === span.span_id)}
          allSpans={spans}
          depth={0}
          selectedSpanId={selectedSpanId}
          onSelect={onSelectSpan}
        />
      ))}
    </div>
  );
}
