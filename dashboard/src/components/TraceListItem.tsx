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
  depth?: number;
  isLast?: boolean;
  compareMode?: boolean;
  checked?: boolean;
  onCheck?: () => void;
  disabled?: boolean;
}

/** Width of the connector gutter in px. */
const GUTTER = 28;

/** Curved ├── / └── connector rendered in the gutter.
 *
 * The elbow is a single bordered div:
 *   - left + bottom border from (left=10, top=0) to (right=0, top=50%)
 *   - border-bottom-left-radius gives the curve
 * For non-last items a thin continuation line extends from 50% to the bottom
 * of the row, keeping the │ column alive for the next sibling.
 */
function Connector({ isLast }: { isLast: boolean }) {
  const C = "var(--connector-color)";
  const THICK = 2;
  const RADIUS = 10;

  return (
    <div className="relative flex-shrink-0" style={{ width: GUTTER }}>
      {/* Curved elbow: top → midpoint with rightward arm */}
      <div
        style={{
          position: "absolute",
          left: 10,
          top: 0,
          bottom: "50%",
          right: 0,
          borderLeft: `${THICK}px solid ${C}`,
          borderBottom: `${THICK}px solid ${C}`,
          borderBottomLeftRadius: RADIUS,
        }}
      />
      {/* Continuation line below midpoint — only when more siblings follow */}
      {!isLast && (
        <div
          style={{
            position: "absolute",
            left: 10,
            top: "50%",
            bottom: 0,
            width: THICK,
            background: C,
          }}
        />
      )}
    </div>
  );
}

export function TraceListItem({
  trace,
  selected,
  onClick,
  depth = 0,
  isLast = false,
  compareMode = false,
  checked = false,
  onCheck,
  disabled = false,
}: Props) {
  const isChild = depth > 0;

  return (
    <div className={`flex min-w-0 ${disabled ? "opacity-30 pointer-events-none" : ""}`}>
      {isChild && <Connector isLast={isLast} />}

      {compareMode && (
        <button
          onClick={(e) => {
            e.stopPropagation();
            if (!disabled) onCheck?.();
          }}
          disabled={disabled}
          className="flex w-8 shrink-0 items-center justify-center border-b border-border"
        >
          <span
            className={`flex h-4 w-4 items-center justify-center rounded border text-[10px] font-bold transition-colors ${
              checked
                ? "border-accent bg-accent text-white"
                : "border-text-muted/40 text-transparent hover:border-text-muted"
            }`}
          >
            ✓
          </span>
        </button>
      )}

      <div
        onClick={compareMode ? (disabled ? undefined : onCheck) : onClick}
        className={`min-w-0 flex-1 cursor-pointer border-b border-border px-3 transition-colors hover:bg-panel ${
          selected && !compareMode ? "border-l-2 border-l-accent bg-panel" : ""
        } ${checked ? "bg-accent/5" : ""} ${isChild ? "py-1.5" : "py-2.5"}`}
      >
        {/* Name row */}
        <div className="flex items-center justify-between gap-2">
          <div className="flex min-w-0 items-center gap-1.5">
            {isChild && (
              <span className="flex-shrink-0 text-[10px] font-medium text-accent">↺</span>
            )}
            <span
              className={`truncate font-medium text-text-primary ${isChild ? "text-[12px]" : ""}`}
              title={trace.name}
            >
              {/* Strip the leading "↺ " we add server-side — icon shown separately */}
              {isChild ? trace.name.replace(/^↺\s*/, "") : trace.name}
            </span>
          </div>
          <StatusBadge status={trace.status} />
        </div>

        {/* Meta row */}
        <div className="mt-0.5 flex flex-wrap items-center gap-x-3 text-[11px] text-text-muted">
          <span className="font-mono">{trace.trace_id.slice(0, 8)}</span>
          <span>{formatDuration(trace.duration_ms)}</span>
          {!isChild && <span>{trace.span_count} spans</span>}
          {trace.total_tokens != null && (
            <span>{trace.total_tokens.toLocaleString()} tok</span>
          )}
          {trace.total_cost_usd != null && (
            <span>${trace.total_cost_usd.toFixed(4)}</span>
          )}
          {trace.tags?.["traceai.experiment"] && (
            <span
              className="rounded bg-violet-500/15 px-1 py-0.5 text-[10px] font-medium text-violet-400"
              title={`Experiment: ${trace.tags["traceai.experiment"]}`}
            >
              ⇄ {trace.tags["traceai.experiment"]}
            </span>
          )}
        </div>

        {/* Timestamp — only for root traces */}
        {!isChild && (
          <div className="mt-0.5 text-[11px] text-text-muted">{formatTime(trace.started_at)}</div>
        )}
      </div>
    </div>
  );
}
