import type { Trace } from "../types/api";

function formatCost(usd: number | null | undefined): string {
  if (usd == null) return "—";
  if (usd < 0.01) return `$${usd.toFixed(6)}`;
  return `$${usd.toFixed(4)}`;
}

interface Props {
  trace: Trace;
  onSelectTrace: (id: string) => void;
}

export function ReplayBanner({ trace, onSelectTrace }: Props) {
  const meta = trace.metadata as Record<string, unknown> | null;
  if (!meta?.replay_of_trace) return null;

  const originalTraceId = meta.replay_of_trace as string;
  const originalModel = (meta.original_model as string | undefined) ?? "original";
  const replayModel = (meta.replay_model as string | undefined) ?? "replay";
  const originalCost = meta.original_cost_usd as number | null | undefined;
  const replayCost = meta.replay_cost_usd as number | null | undefined;
  const originalTokens = (meta.original_tokens as number | undefined) ?? 0;
  const replayTokens = (meta.replay_tokens as number | undefined) ?? 0;

  const sameModel = originalModel === replayModel;

  let savingsEl: React.ReactNode = null;
  if (sameModel) {
    savingsEl = (
      <span className="text-[10px] italic text-text-muted">
        ℹ Same model — token/cost variation is normal (LLMs are non-deterministic)
      </span>
    );
  } else if (originalCost != null && replayCost != null && originalCost > 0) {
    const pct = ((originalCost - replayCost) / originalCost) * 100;
    const cheaper = pct > 0;
    savingsEl = (
      <span className={`font-semibold ${cheaper ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400"}`}>
        {cheaper ? "−" : "+"}
        {Math.abs(pct).toFixed(0)}% cost
        {originalTokens > 0 && (
          <span className="font-normal text-text-muted">
            {" · "}
            {replayTokens > originalTokens ? "+" : "−"}
            {Math.abs(replayTokens - originalTokens).toLocaleString()} tok
          </span>
        )}
      </span>
    );
  }

  return (
    <div className="border-b border-accent/30 bg-accent/10 px-4 py-2 text-xs text-text-secondary">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="font-semibold text-accent">↺ Replayed</span>
        <span>
          from{" "}
          <button
            onClick={() => onSelectTrace(originalTraceId)}
            className="font-mono text-accent underline-offset-2 hover:underline"
          >
            {originalTraceId.slice(0, 8)}
          </button>
        </span>
        <span className="text-text-muted">
          {originalModel} → {replayModel}
        </span>
        <span className="ml-auto flex flex-wrap items-center gap-3">
          <span>
            Original: <span className="text-text-primary">{formatCost(originalCost)}</span>
            {originalTokens > 0 && (
              <span className="text-text-muted"> · {originalTokens.toLocaleString()} tok</span>
            )}
          </span>
          <span>
            Replay: <span className="text-text-primary">{formatCost(replayCost)}</span>
            {replayTokens > 0 && (
              <span className="text-text-muted"> · {replayTokens.toLocaleString()} tok</span>
            )}
          </span>
          {savingsEl}
        </span>
      </div>
    </div>
  );
}
