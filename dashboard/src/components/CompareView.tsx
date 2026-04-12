import { useEffect, useMemo, useState } from "react";
import type { Span, SpanKind, Trace } from "../types/api";
import { fetchSpans, fetchTrace } from "../api/client";
import { diffLines, similarity } from "../utils/diff";
import {
  areComparable,
  extractOutputText,
  matchSpansForFamily,
  type DiffStatus,
} from "../utils/compare";

// ── Helpers ─────────────────────────────────────────────────────────────────

const KIND_DOT: Record<SpanKind, string> = {
  llm_call: "#818cf8",
  agent_step: "#60a5fa",
  tool_call: "#4ade80",
  memory_read: "#c084fc",
  memory_write: "#c084fc",
  retrieval: "#22d3ee",
  embedding: "#facc15",
  custom: "#94a3b8",
};

function fmt(ms: number | null): string {
  if (ms == null) return "—";
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

function cost(usd: number | null | undefined): string {
  if (usd == null) return "—";
  if (usd < 0.01) return `$${usd.toFixed(6)}`;
  return `$${usd.toFixed(4)}`;
}

function tok(n: number | null | undefined): string {
  if (n == null) return "—";
  return n.toLocaleString();
}

function deltaStr(
  a: number | null | undefined,
  b: number | null | undefined,
): string | null {
  if (a == null || b == null || a === 0) return null;
  const pct = ((b - a) / Math.abs(a)) * 100;
  const sign = pct > 0 ? "+" : "";
  return `${sign}${pct.toFixed(1)}%`;
}

function spanModel(span: Span): string {
  return (
    ((span.metadata as Record<string, unknown> | null)?.[
      "gen_ai.request.model"
    ] as string | undefined) ??
    ((span.inputs as Record<string, unknown> | null)?.model as
      | string
      | undefined) ??
    ""
  );
}

// ── Sub-components ──────────────────────────────────────────────────────────

const STATUS_ICON: Record<
  DiffStatus,
  { char: string; cls: string; tip: string }
> = {
  identical: { char: "=", cls: "text-green-500", tip: "Outputs identical" },
  modified: { char: "~", cls: "text-amber-400", tip: "Outputs differ" },
  "a-only": { char: "A", cls: "text-red-400", tip: "Only in Trace A" },
  "b-only": { char: "B", cls: "text-blue-400", tip: "Only in Trace B" },
};

function StatCell({
  label,
  valA,
  valB,
  delta,
}: {
  label: string;
  valA: string;
  valB: string;
  delta: string | null;
}) {
  const isNeg = delta?.startsWith("-");
  return (
    <div className="flex flex-col items-center gap-0.5">
      <span className="text-[9px] uppercase tracking-wider text-text-muted">
        {label}
      </span>
      <div className="flex items-center gap-2 text-xs">
        <span className="font-mono text-text-primary">{valA}</span>
        <span className="text-text-muted">vs</span>
        <span className="font-mono text-text-primary">{valB}</span>
      </div>
      {delta && (
        <span
          className={`text-[10px] font-semibold ${isNeg ? "text-green-500" : "text-red-400"}`}
        >
          {delta}
        </span>
      )}
    </div>
  );
}

function SplitDiff({ textA, textB }: { textA: string; textB: string }) {
  const lines = diffLines(textA, textB);

  const left: Array<{ text: string; highlighted: boolean }> = [];
  const right: Array<{ text: string; highlighted: boolean }> = [];

  for (const line of lines) {
    if (line.type === "equal") {
      left.push({ text: line.text, highlighted: false });
      right.push({ text: line.text, highlighted: false });
    } else if (line.type === "remove") {
      left.push({ text: line.text, highlighted: true });
    } else {
      right.push({ text: line.text, highlighted: true });
    }
  }

  const Column = ({
    lines: colLines,
    side,
  }: {
    lines: Array<{ text: string; highlighted: boolean }>;
    side: "a" | "b";
  }) => (
    <div className="flex-1 overflow-x-auto">
      <div className="mb-1 px-2 text-[9px] font-semibold uppercase tracking-wider text-text-muted">
        Trace {side.toUpperCase()}
      </div>
      {colLines.map((l, i) => (
        <div
          key={i}
          className={`px-2 ${
            l.highlighted
              ? side === "a"
                ? "bg-red-500/10 dark:bg-red-500/15"
                : "bg-green-500/10 dark:bg-green-500/15"
              : ""
          }`}
        >
          <span
            className={`font-mono text-[11px] leading-[20px] ${
              l.highlighted
                ? side === "a"
                  ? "text-red-300 dark:text-red-300"
                  : "text-green-300 dark:text-green-300"
                : "text-text-secondary"
            }`}
          >
            {l.text || "\u00A0"}
          </span>
        </div>
      ))}
    </div>
  );

  return (
    <div className="flex gap-0 overflow-hidden rounded-lg border border-border">
      <Column lines={left} side="a" />
      <div className="w-px shrink-0 bg-border" />
      <Column lines={right} side="b" />
    </div>
  );
}

// ── Main component ──────────────────────────────────────────────────────────

interface Props {
  traceIds: [string, string];
  onClose: () => void;
}

export function CompareView({ traceIds, onClose }: Props) {
  const [traceA, setTraceA] = useState<Trace | null>(null);
  const [traceB, setTraceB] = useState<Trace | null>(null);
  const [spansA, setSpansA] = useState<Span[]>([]);
  const [spansB, setSpansB] = useState<Span[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedIdx, setSelectedIdx] = useState<number | null>(null);

  useEffect(() => {
    setLoading(true);
    setSelectedIdx(null);
    Promise.all([
      fetchTrace(traceIds[0]),
      fetchTrace(traceIds[1]),
      fetchSpans(traceIds[0]),
      fetchSpans(traceIds[1]),
    ])
      .then(([tA, tB, sA, sB]) => {
        // Sort so the older (original) trace is always A
        if (new Date(tA.started_at) > new Date(tB.started_at)) {
          setTraceA(tB);
          setTraceB(tA);
          setSpansA(sB);
          setSpansB(sA);
        } else {
          setTraceA(tA);
          setTraceB(tB);
          setSpansA(sA);
          setSpansB(sB);
        }
      })
      .finally(() => setLoading(false));
  }, [traceIds[0], traceIds[1]]);

  const comparable = traceA && traceB ? areComparable(traceA, traceB) : false;

  const pairs = useMemo(() => {
    if (!traceA || !traceB) return [];
    return matchSpansForFamily(traceA, spansA, traceB, spansB);
  }, [traceA, traceB, spansA, spansB]);

  const modifiedCount = pairs.filter((p) => p.status === "modified").length;
  const identicalCount = pairs.filter((p) => p.status === "identical").length;
  const aOnlyCount = pairs.filter((p) => p.status === "a-only").length;
  const bOnlyCount = pairs.filter((p) => p.status === "b-only").length;

  const modelNameA = spansA.find((s) => s.kind === "llm_call");
  const modelNameB = spansB.find((s) => s.kind === "llm_call");
  const mA = modelNameA ? spanModel(modelNameA) : "";
  const mB = modelNameB ? spanModel(modelNameB) : "";

  const selectedPair = selectedIdx != null ? pairs[selectedIdx] : null;

  // Overall output similarity
  const overallSim = useMemo(() => {
    const matched = pairs.filter((p) => p.spanA && p.spanB);
    if (matched.length === 0) return null;
    const total = matched.reduce(
      (acc, p) =>
        acc +
        similarity(
          extractOutputText(p.spanA!),
          extractOutputText(p.spanB!),
        ),
      0,
    );
    return total / matched.length;
  }, [pairs]);

  if (loading) {
    return (
      <div className="flex flex-1 items-center justify-center text-xs text-text-muted">
        Loading comparison…
      </div>
    );
  }

  if (!traceA || !traceB) {
    return (
      <div className="flex flex-1 items-center justify-center text-xs text-text-muted">
        Failed to load traces
      </div>
    );
  }

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      {/* ── Header ──────────────────────────────────────────────── */}
      <div className="flex shrink-0 items-center gap-3 border-b border-border bg-panel px-4 py-2">
        <button
          onClick={onClose}
          className="rounded px-2 py-0.5 text-xs text-text-muted hover:bg-border hover:text-text-secondary"
        >
          ← Back
        </button>
        <h2 className="text-sm font-semibold text-text-primary">
          Trace Comparison
        </h2>
      </div>

      {/* ── Incompatible warning ────────────────────────────────── */}
      {!comparable && (
        <div className="flex shrink-0 items-center gap-2 border-b border-amber-500/30 bg-amber-500/10 px-4 py-2 text-xs text-amber-300">
          <span className="text-base">⚠</span>
          <span>
            These traces are not replay-linked — span matching may be
            inaccurate. For meaningful comparison, replay one trace with a
            different model first.
          </span>
        </div>
      )}

      {/* ── Summary strip ───────────────────────────────────────── */}
      <div className="shrink-0 border-b border-border bg-background px-4 py-3">
        <div className="mb-3 flex items-stretch gap-3">
          <div className="flex-1 rounded-lg border border-border bg-panel px-3 py-2">
            <div className="mb-0.5 text-[9px] font-semibold uppercase tracking-wider text-accent">
              Trace A
            </div>
            <div className="truncate text-xs font-medium text-text-primary">
              {traceA.name}
            </div>
            {mA && (
              <div className="mt-0.5 font-mono text-[10px] text-text-muted">
                {mA}
              </div>
            )}
          </div>
          <div className="flex items-center text-lg text-text-muted">⇄</div>
          <div className="flex-1 rounded-lg border border-border bg-panel px-3 py-2">
            <div className="mb-0.5 text-[9px] font-semibold uppercase tracking-wider text-accent">
              Trace B
            </div>
            <div className="truncate text-xs font-medium text-text-primary">
              {traceB.name}
            </div>
            {mB && (
              <div className="mt-0.5 font-mono text-[10px] text-text-muted">
                {mB}
              </div>
            )}
          </div>
        </div>

        <div className="flex flex-wrap items-center justify-center gap-6">
          <StatCell
            label="Cost"
            valA={cost(traceA.total_cost_usd)}
            valB={cost(traceB.total_cost_usd)}
            delta={deltaStr(traceA.total_cost_usd, traceB.total_cost_usd)}
          />
          <StatCell
            label="Tokens"
            valA={tok(traceA.total_tokens)}
            valB={tok(traceB.total_tokens)}
            delta={deltaStr(traceA.total_tokens, traceB.total_tokens)}
          />
          <StatCell
            label="Duration"
            valA={fmt(traceA.duration_ms)}
            valB={fmt(traceB.duration_ms)}
            delta={deltaStr(traceA.duration_ms, traceB.duration_ms)}
          />
          <StatCell
            label="Spans"
            valA={String(traceA.span_count)}
            valB={String(traceB.span_count)}
            delta={null}
          />
        </div>
      </div>

      {/* ── Match summary bar ───────────────────────────────────── */}
      <div className="flex shrink-0 items-center gap-3 border-b border-border bg-background px-4 py-1.5 text-[10px] text-text-muted">
        <span>
          <span className="font-semibold text-green-500">
            {identicalCount}
          </span>{" "}
          identical
        </span>
        <span>
          <span className="font-semibold text-amber-400">{modifiedCount}</span>{" "}
          modified
        </span>
        <span>
          <span className="font-semibold text-red-400">{aOnlyCount}</span>{" "}
          A-only
        </span>
        <span>
          <span className="font-semibold text-blue-400">{bOnlyCount}</span>{" "}
          B-only
        </span>
        {overallSim != null && (
          <span className="ml-auto">
            Similarity:{" "}
            <span className="font-semibold text-text-primary">
              {(overallSim * 100).toFixed(0)}%
            </span>
          </span>
        )}
      </div>

      {/* ── Main pane ───────────────────────────────────────────── */}
      <div className="flex flex-1 overflow-hidden">
        {/* Span match list */}
        <div className="w-52 shrink-0 overflow-y-auto border-r border-border">
          <div className="border-b border-border px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wide text-text-muted">
            Spans ({pairs.length})
          </div>
          {pairs.map((pair, i) => {
            const st = STATUS_ICON[pair.status];
            const selected = selectedIdx === i;
            return (
              <button
                key={i}
                onClick={() => setSelectedIdx(i)}
                className={`flex w-full items-center gap-1.5 border-b border-border/30 px-3 py-1.5 text-left text-xs transition-colors hover:bg-panel/60 ${
                  selected ? "bg-panel border-l-2 border-l-accent" : ""
                }`}
              >
                <span
                  className={`w-3 shrink-0 text-center font-mono text-[10px] font-bold ${st.cls}`}
                  title={st.tip}
                >
                  {st.char}
                </span>
                <span
                  className="h-2 w-2 shrink-0 rounded-full"
                  style={{ backgroundColor: KIND_DOT[pair.kind] }}
                />
                <span className="truncate text-text-secondary">
                  {pair.name}
                </span>
              </button>
            );
          })}
        </div>

        {/* Diff detail */}
        <div className="flex-1 overflow-y-auto p-4">
          {!selectedPair ? (
            <div className="flex h-full flex-col items-center justify-center gap-2 text-text-muted">
              <span className="text-2xl">⇄</span>
              <span className="text-xs">Select a span to view the diff</span>
            </div>
          ) : selectedPair.status === "a-only" ? (
            <div>
              <div className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-red-400">
                Only in Trace A
              </div>
              <SpanSnapshot span={selectedPair.spanA!} />
            </div>
          ) : selectedPair.status === "b-only" ? (
            <div>
              <div className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-blue-400">
                Only in Trace B
              </div>
              <SpanSnapshot span={selectedPair.spanB!} />
            </div>
          ) : selectedPair.status === "identical" ? (
            <div>
              <SpanMetaCompare a={selectedPair.spanA!} b={selectedPair.spanB!} />
              <div className="mt-4 flex flex-col items-center justify-center gap-1 rounded-lg border border-green-500/20 bg-green-500/5 py-6 text-green-500">
                <span className="text-lg">=</span>
                <span className="text-xs font-medium">
                  Outputs are identical
                </span>
              </div>
            </div>
          ) : (
            <div>
              <SpanMetaCompare a={selectedPair.spanA!} b={selectedPair.spanB!} />
              <div className="mt-3">
                <SplitDiff
                  textA={extractOutputText(selectedPair.spanA!)}
                  textB={extractOutputText(selectedPair.spanB!)}
                />
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Inline helpers ──────────────────────────────────────────────────────────

function SpanMetaCompare({ a, b }: { a: Span; b: Span }) {
  const mA = (a.metadata ?? {}) as Record<string, unknown>;
  const mB = (b.metadata ?? {}) as Record<string, unknown>;
  const tokA =
    ((mA["gen_ai.usage.input_tokens"] as number) ?? 0) +
    ((mA["gen_ai.usage.output_tokens"] as number) ?? 0);
  const tokB =
    ((mB["gen_ai.usage.input_tokens"] as number) ?? 0) +
    ((mB["gen_ai.usage.output_tokens"] as number) ?? 0);
  const costA = mA["gen_ai.usage.call_cost_usd"] as number | undefined;
  const costB = mB["gen_ai.usage.call_cost_usd"] as number | undefined;
  const sim = similarity(extractOutputText(a), extractOutputText(b));

  return (
    <div className="flex flex-wrap items-center gap-4 rounded-lg border border-border bg-panel/40 px-3 py-2 text-[11px]">
      <div>
        <span className="text-text-muted">Model: </span>
        <span className="font-mono text-text-primary">
          {spanModel(a) || "—"}
        </span>
        <span className="text-text-muted"> vs </span>
        <span className="font-mono text-text-primary">
          {spanModel(b) || "—"}
        </span>
      </div>
      <div>
        <span className="text-text-muted">Tokens: </span>
        <span className="text-text-primary">{tok(tokA)}</span>
        <span className="text-text-muted"> vs </span>
        <span className="text-text-primary">{tok(tokB)}</span>
      </div>
      {(costA != null || costB != null) && (
        <div>
          <span className="text-text-muted">Cost: </span>
          <span className="text-text-primary">{cost(costA)}</span>
          <span className="text-text-muted"> vs </span>
          <span className="text-text-primary">{cost(costB)}</span>
        </div>
      )}
      <div>
        <span className="text-text-muted">Duration: </span>
        <span className="text-text-primary">{fmt(a.duration_ms)}</span>
        <span className="text-text-muted"> vs </span>
        <span className="text-text-primary">{fmt(b.duration_ms)}</span>
      </div>
      <div className="ml-auto">
        <span className="text-text-muted">Similarity: </span>
        <span className="font-semibold text-text-primary">
          {(sim * 100).toFixed(0)}%
        </span>
      </div>
    </div>
  );
}

function SpanSnapshot({ span }: { span: Span }) {
  const text = extractOutputText(span);
  return (
    <div className="rounded-lg border border-border">
      <div className="flex flex-wrap gap-3 border-b border-border/60 px-3 py-2 text-[11px] text-text-muted">
        <span>
          Kind: <span className="text-text-primary">{span.kind}</span>
        </span>
        <span>
          Model:{" "}
          <span className="font-mono text-text-primary">
            {spanModel(span) || "—"}
          </span>
        </span>
        <span>
          Duration:{" "}
          <span className="text-text-primary">{fmt(span.duration_ms)}</span>
        </span>
      </div>
      {text ? (
        <pre className="max-h-80 overflow-auto whitespace-pre-wrap p-3 font-mono text-[11px] leading-[20px] text-text-secondary">
          {text}
        </pre>
      ) : (
        <div className="px-3 py-4 text-center text-xs text-text-muted">
          No output
        </div>
      )}
    </div>
  );
}
