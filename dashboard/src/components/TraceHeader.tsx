import { useState } from "react";
import type { Trace } from "../types/api";
import { replayTrace } from "../api/client";
import { StatusBadge } from "./StatusBadge";
import { ModelPicker } from "./ModelPicker";

function formatDuration(ms: number | null): string {
  if (ms == null) return "—";
  if (ms < 1000) return `${ms.toFixed(0)}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

function formatCost(usd: number | null): string {
  if (usd == null) return "";
  if (usd < 0.01) return `$${usd.toFixed(6)}`;
  return `$${usd.toFixed(4)}`;
}

interface Props {
  trace: Trace;
  originalModel?: string;
  onReplaySuccess: (traceId: string) => void;
}

export function TraceHeader({ trace, originalModel, onReplaySuccess }: Props) {
  const [cascadeModel, setCascadeModel] = useState("gpt-4o-mini");
  const [cascadeProvider, setCascadeProvider] = useState<string | undefined>(undefined);
  const [cascading, setCascading] = useState(false);
  const [cascadeError, setCascadeError] = useState<string | null>(null);
  const [showCascade, setShowCascade] = useState(false);
  const [sameModelAlert, setSameModelAlert] = useState(false);

  // Only show cascade button for traces with LLM calls that aren't themselves replays
  const isReplay = Boolean(
    (trace.metadata as Record<string, unknown> | null)?.replay_of_trace,
  );
  const canCascade = trace.llm_call_count > 0 && !isReplay;

  async function handleCascade() {
    if (originalModel && cascadeModel === originalModel) {
      setSameModelAlert(true);
      return;
    }
    setCascading(true);
    setCascadeError(null);
    try {
      const result = await replayTrace(trace.trace_id, {
        model: cascadeModel,
        ...(cascadeProvider ? { provider: cascadeProvider } : {}),
      });
      onReplaySuccess(result.trace_id);
    } catch (err) {
      setCascadeError(err instanceof Error ? err.message : "Cascade replay failed");
    } finally {
      setCascading(false);
    }
  }

  return (
    <>
      {/* Same-model guard modal */}
      {sameModelAlert && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="w-80 rounded-xl border border-border bg-panel p-5 shadow-2xl text-center">
            <div className="mb-2 text-3xl">↩</div>
            <h3 className="mb-1 text-sm font-semibold text-text-primary">Same Model Selected</h3>
            <p className="mb-4 text-xs text-text-muted">
              You selected{" "}
              <span className="font-mono text-text-primary">{cascadeModel}</span> — the same
              model as the original trace. Replaying won't produce a meaningful comparison.
            </p>
            <button
              onClick={() => setSameModelAlert(false)}
              className="rounded-lg bg-accent px-5 py-1.5 text-xs font-semibold text-white hover:bg-accent/80"
            >
              Got it
            </button>
          </div>
        </div>
      )}
    <div className="border-b border-border bg-panel px-4 py-2.5">
      <div className="flex items-center gap-3">
        <h2 className="truncate text-sm font-semibold text-text-primary">{trace.name}</h2>
        <StatusBadge status={trace.status} />
      </div>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-text-muted">
        <span>
          ID: <span className="font-mono text-text-secondary">{trace.trace_id.slice(0, 16)}</span>
        </span>
        <span>Duration: {formatDuration(trace.duration_ms)}</span>
        <span>Spans: {trace.span_count}</span>
        <span>LLM calls: {trace.llm_call_count}</span>
        {trace.total_tokens != null && (
          <span>Tokens: {trace.total_tokens.toLocaleString()}</span>
        )}
        {trace.total_cost_usd != null && (
          <span>Cost: {formatCost(trace.total_cost_usd)}</span>
        )}
        <span>
          {new Date(trace.started_at).toLocaleString(undefined, {
            month: "short",
            day: "numeric",
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
          })}
        </span>
      </div>

      {/* Trace-level cascade replay — only for original traces with LLM calls */}
      {canCascade && (
        <div className="mt-1.5 border-t border-border/40 pt-1.5">
          {!showCascade ? (
            <button
              onClick={() => setShowCascade(true)}
              className="text-[10px] text-text-muted hover:text-accent"
            >
              ↺ Compare with another model…
            </button>
          ) : (
            <div>
              <div className="flex flex-wrap items-center gap-1.5">
                <ModelPicker value={cascadeModel} onChange={(m, p) => { setCascadeModel(m); setCascadeProvider(p); }} disabled={cascading} />
                <button
                  onClick={() => void handleCascade()}
                  disabled={cascading}
                  title={`Re-run all ${trace.llm_call_count} llm_call spans with the selected model`}
                  className="rounded bg-panel px-2 py-0.5 text-xs font-semibold text-accent ring-1 ring-accent/40 hover:bg-accent/10 disabled:opacity-50"
                >
                  {cascading ? "Replaying…" : "↺ Replay All LLM Calls"}
                </button>
                <button
                  onClick={() => setShowCascade(false)}
                  className="ml-auto text-[10px] text-text-muted hover:text-text-secondary"
                >
                  ✕
                </button>
              </div>
              {cascadeError && (
                <div className="mt-1 rounded border border-red-300 bg-red-50 px-2 py-1 text-xs text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-400">
                  {cascadeError}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
    </>
  );
}
