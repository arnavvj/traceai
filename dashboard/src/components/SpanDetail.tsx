import type { ReactNode } from "react";
import type { Span } from "../types/api";
import { StatusBadge } from "./StatusBadge";
import { JsonViewer } from "./JsonViewer";

function formatDuration(ms: number | null): string {
  if (ms == null) return "—";
  if (ms < 1000) return `${ms.toFixed(0)}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

interface Props {
  span: Span | null;
}

export function SpanDetail({ span }: Props) {
  if (!span) {
    return (
      <div className="flex flex-1 items-center justify-center text-xs text-text-muted">
        Select a span to inspect
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto p-4">
      <div className="mb-4">
        <table className="w-full text-xs">
          <tbody>
            {(
              [
                ["Span ID", <span className="font-mono">{span.span_id.slice(0, 16)}</span>],
                ["Kind", <span className="font-mono">{span.kind}</span>],
                ["Status", <StatusBadge status={span.status} />],
                ["Started", new Date(span.started_at).toLocaleString()],
                ["Duration", formatDuration(span.duration_ms)],
                ...(span.parent_span_id
                  ? [["Parent", <span className="font-mono">{span.parent_span_id.slice(0, 16)}</span>]]
                  : []),
              ] as [string, ReactNode][]
            ).map(([label, value], i) => (
              <tr key={i} className="border-b border-border">
                <td className="py-1.5 pr-4 text-text-muted">{label}</td>
                <td className="py-1.5 text-text-primary">{value}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <JsonViewer data={span.inputs} label="Inputs" />
      <JsonViewer data={span.outputs} label="Outputs" />
      <JsonViewer data={span.metadata} label="Metadata" />

      {span.error && (
        <div className="rounded border border-red-800 bg-red-900/20 p-3 text-xs">
          <div className="mb-1 font-semibold text-red-400">
            {span.error.exception_type}: {span.error.message}
          </div>
          {span.error.traceback && (
            <pre className="mt-2 overflow-x-auto whitespace-pre-wrap text-red-300/80 text-[11px] leading-relaxed">
              {span.error.traceback}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}
