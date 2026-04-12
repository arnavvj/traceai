import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import type { Message, Span } from "../types/api";
import { replaySpan } from "../api/client";
import { StatusBadge } from "./StatusBadge";
import { JsonViewer } from "./JsonViewer";
import { ModelPicker } from "./ModelPicker";

function formatDuration(ms: number | null): string {
  if (ms == null) return "—";
  if (ms < 1000) return `${ms.toFixed(0)}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

const ROLE_STYLES: Record<string, string> = {
  system:    "bg-purple-100 text-purple-700 border border-purple-300 dark:bg-purple-900/50 dark:text-purple-300 dark:border-purple-800",
  user:      "bg-blue-100 text-blue-700 border border-blue-300 dark:bg-blue-900/50 dark:text-blue-300 dark:border-blue-800",
  assistant: "bg-green-100 text-green-700 border border-green-300 dark:bg-green-900/50 dark:text-green-300 dark:border-green-800",
};

interface Props {
  span: Span | null;
  onReplaySuccess: (traceId: string, spanId?: string) => void;
}

export function SpanDetail({ span, onReplaySuccess }: Props) {
  const [playground, setPlayground] = useState(false);
  const [editedMessages, setEditedMessages] = useState<Message[]>([]);
  const [replaying, setReplaying] = useState(false);
  const [replayError, setReplayError] = useState<string | null>(null);
  const [replayModel, setReplayModel] = useState("");
  const [replayProvider, setReplayProvider] = useState<string | undefined>(undefined);
  const [sameModelAlert, setSameModelAlert] = useState(false);

  useEffect(() => {
    setPlayground(false);
    setEditedMessages([]);
    setReplaying(false);
    setReplayError(null);
    // Default to the model used in the original span
    const m =
      (span?.inputs as { model?: string } | null)?.model ??
      (span?.metadata as { "gen_ai.request.model"?: string } | null)?.["gen_ai.request.model"] ??
      "";
    setReplayModel(m);
    setReplayProvider(undefined);
  }, [span?.span_id]);

  if (!span) {
    return (
      <div className="flex flex-1 items-center justify-center text-xs text-text-muted">
        Select a span to inspect
      </div>
    );
  }

  const isLlmCall = span.kind === "llm_call";
  const rawMessages = ((span.inputs as { messages?: Message[] } | null)?.messages ?? []);
  const originalModel =
    (span.inputs as { model?: string } | null)?.model ??
    (span.metadata as { "gen_ai.request.model"?: string } | null)?.["gen_ai.request.model"] ??
    "";

  async function handleReplay(messagesOverride?: Message[]) {
    if (replayModel && replayModel === originalModel) {
      setSameModelAlert(true);
      return;
    }
    setReplaying(true);
    setReplayError(null);
    try {
      const req: { messages?: Message[]; model?: string; provider?: string } = {};
      if (messagesOverride) req.messages = messagesOverride;
      if (replayModel) req.model = replayModel;
      if (replayProvider) req.provider = replayProvider;
      const result = await replaySpan(span!.span_id, req);
      onReplaySuccess(result.trace_id, result.span_id);
    } catch (err) {
      setReplayError(err instanceof Error ? err.message : "Replay failed");
    } finally {
      setReplaying(false);
    }
  }

  function startPlayground() {
    setEditedMessages(rawMessages.map((m) => ({ ...m })));
    setPlayground(true);
  }

  return (
    <div className="flex-1 overflow-y-auto p-3">
      {/* Same-model guard modal */}
      {sameModelAlert && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="w-80 rounded-xl border border-border bg-panel p-5 shadow-2xl text-center">
            <div className="mb-2 text-3xl">↩</div>
            <h3 className="mb-1 text-sm font-semibold text-text-primary">Same Model Selected</h3>
            <p className="mb-4 text-xs text-text-muted">
              You selected{" "}
              <span className="font-mono text-text-primary">{replayModel}</span> — the same
              model as the original. Replaying won't produce a meaningful comparison.
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
      {/* Summary table */}
      <div className="mb-3">
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
              <tr key={i} className="border-b border-border/60">
                <td className="py-1 pr-4 text-text-muted">{label}</td>
                <td className="py-1 text-text-primary">{value}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Replay toolbar — only for llm_call spans */}
      {isLlmCall && (
        <div className="mb-3 border-t border-border/40 pt-2">
          <div className="flex flex-wrap items-center gap-1.5">
            <ModelPicker value={replayModel} onChange={(m, p) => { setReplayModel(m); setReplayProvider(p); }} disabled={replaying} />
            <div className="ml-auto flex gap-1.5">
              {playground ? (
                <>
                  <button
                    onClick={() => setPlayground(false)}
                    className="rounded px-2 py-0.5 text-xs text-text-secondary hover:bg-border"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={() => void handleReplay(editedMessages)}
                    disabled={replaying}
                    className="rounded bg-accent px-2 py-0.5 text-xs font-semibold text-white hover:bg-accent/80 disabled:opacity-50"
                  >
                    {replaying ? "Running…" : "▶ Run"}
                  </button>
                </>
              ) : (
                <>
                  <button
                    onClick={startPlayground}
                    className="rounded px-2 py-0.5 text-xs text-text-muted hover:bg-border hover:text-text-secondary"
                  >
                    ✎ Edit
                  </button>
                  <button
                    onClick={() => void handleReplay()}
                    disabled={replaying}
                    title="Re-run this span with the selected model"
                    className="rounded bg-accent px-2 py-0.5 text-xs font-semibold text-white hover:bg-accent/80 disabled:opacity-50"
                  >
                    {replaying ? "Running…" : "▶ Replay Span"}
                  </button>
                </>
              )}
            </div>
          </div>
          {replayError && (
            <div className="mt-1 rounded border border-red-300 bg-red-50 px-2 py-1 text-xs text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-400">
              {replayError}
            </div>
          )}
        </div>
      )}

      {/* Inputs — editable in playground mode, read-only otherwise */}
      {isLlmCall && playground ? (
        <div className="mb-4">
          <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-text-muted">
            Messages
          </div>
          <div className="flex flex-col gap-2">
            {editedMessages.map((msg, i) => (
              <div key={i} className="rounded border border-border bg-background p-2">
                <span
                  className={`mb-1 inline-block rounded px-1.5 py-0.5 text-[10px] font-medium ${ROLE_STYLES[msg.role] ?? "bg-slate-100 text-slate-600 border border-slate-300 dark:bg-gray-800 dark:text-gray-300 dark:border-gray-700"}`}
                >
                  {msg.role}
                </span>
                <textarea
                  value={msg.content}
                  onChange={(e) => {
                    const updated = editedMessages.map((m, j) =>
                      j === i ? { ...m, content: e.target.value } : m,
                    );
                    setEditedMessages(updated);
                  }}
                  rows={Math.max(3, Math.ceil(msg.content.length / 80))}
                  className="mt-1 w-full resize-y rounded border border-border bg-panel px-2 py-1 font-mono text-xs text-text-primary focus:outline-none focus:ring-1 focus:ring-accent"
                />
              </div>
            ))}
          </div>
        </div>
      ) : (
        <JsonViewer data={span.inputs} label="Inputs" />
      )}

      <JsonViewer data={span.outputs} label="Outputs" />
      <JsonViewer data={span.metadata} label="Metadata" />

      {span.error && (
        <div className="rounded border border-red-300 bg-red-50 p-3 text-xs dark:border-red-800 dark:bg-red-900/20">
          <div className="mb-1 font-semibold text-red-700 dark:text-red-400">
            {span.error.exception_type}: {span.error.message}
          </div>
          {span.error.traceback && (
            <pre className="mt-2 overflow-x-auto whitespace-pre-wrap text-[11px] leading-relaxed text-red-600/80 dark:text-red-300/80">
              {span.error.traceback}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}
