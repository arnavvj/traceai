/**
 * Replay-family detection and span matching for trace comparison.
 *
 * Two traces are "comparable" when they belong to the same replay family —
 * i.e. they share the same ultimate original trace.  Span matching uses
 * structural position (DFS order) for trace replays and the `replay_span`
 * tag for span replays, so that the right spans always appear side-by-side.
 */

import type { Span, SpanKind, Trace } from "../types/api";

// ---------------------------------------------------------------------------
// Replay family
// ---------------------------------------------------------------------------

/**
 * Returns the replay-family root ID for a trace.
 *
 * - New traces carry `tags.replay_root` (set by the server on every replay).
 * - Legacy replays fall back to `metadata.replay_of_trace` (1-level only).
 * - Original traces (no replay lineage) return their own ID.
 */
export function replayFamily(trace: Trace): string {
  if (trace.tags?.replay_root) return trace.tags.replay_root;
  const meta = trace.metadata as Record<string, unknown> | null;
  if (meta?.replay_of_trace) return meta.replay_of_trace as string;
  return trace.trace_id;
}

/** True when two traces share a replay ancestor. */
export function areComparable(a: Trace, b: Trace): boolean {
  if (a.trace_id === b.trace_id) return false;
  return replayFamily(a) === replayFamily(b);
}

// ---------------------------------------------------------------------------
// Span matching
// ---------------------------------------------------------------------------

export type DiffStatus = "identical" | "modified" | "a-only" | "b-only";

export interface SpanPair {
  spanA: Span | null;
  spanB: Span | null;
  kind: SpanKind;
  name: string;
  status: DiffStatus;
}

/** Extract the primary textual output from a span for diffing. */
export function extractOutputText(span: Span): string {
  if (!span.outputs) return "";
  const o = span.outputs as Record<string, unknown>;
  if (typeof o.content === "string") return o.content;
  return JSON.stringify(span.outputs, null, 2);
}

function deriveStatus(a: Span, b: Span): DiffStatus {
  return extractOutputText(a) === extractOutputText(b) ? "identical" : "modified";
}

/** Flatten spans depth-first, mirroring the tree traversal order. */
function flattenDFS(
  spans: Span[],
  parentId: string | null = null,
): Span[] {
  const children = spans.filter((s) => s.parent_span_id === parentId);
  const result: Span[] = [];
  for (const child of children) {
    result.push(child);
    result.push(...flattenDFS(spans, child.span_id));
  }
  return result;
}

/** Match two flat span lists index-by-index (best for structural replays). */
function matchByPosition(rawA: Span[], rawB: Span[]): SpanPair[] {
  const flatA = flattenDFS(rawA);
  const flatB = flattenDFS(rawB);
  const pairs: SpanPair[] = [];
  const max = Math.max(flatA.length, flatB.length);

  for (let i = 0; i < max; i++) {
    const a = flatA[i] ?? null;
    const b = flatB[i] ?? null;
    if (a && b) {
      pairs.push({
        spanA: a,
        spanB: b,
        kind: a.kind,
        name: a.name,
        status: deriveStatus(a, b),
      });
    } else if (a) {
      pairs.push({ spanA: a, spanB: null, kind: a.kind, name: a.name, status: "a-only" });
    } else if (b) {
      pairs.push({ spanA: null, spanB: b, kind: b.kind, name: b.name, status: "b-only" });
    }
  }
  return pairs;
}

/**
 * Smart span matching for replay-linked traces.
 *
 * Three cases:
 * 1. **Both full traces** (original or trace-replay): identical hierarchy,
 *    match by DFS position.
 * 2. **Both span replays**: small traces (typically 1 span each),
 *    match by DFS position.
 * 3. **One span replay + one full trace**: use the `replay_span` tag to
 *    anchor the replayed span to the correct position in the full trace.
 *    If the anchor can't be found by span_id (e.g. comparing a span replay
 *    to a *different* trace replay), fall back to input-message matching.
 */
export function matchSpansForFamily(
  traceA: Trace,
  spansA: Span[],
  traceB: Trace,
  spansB: Span[],
): SpanPair[] {
  const replaySpanA = traceA.tags?.replay_span;
  const replaySpanB = traceB.tags?.replay_span;

  // Case 1 & 2: both are the same "type" of trace → positional match
  if ((!replaySpanA && !replaySpanB) || (replaySpanA && replaySpanB)) {
    return matchByPosition(spansA, spansB);
  }

  // Case 3: one is a span replay, other is a full trace
  const isASpanReplay = Boolean(replaySpanA);
  const fullSpans = isASpanReplay ? spansB : spansA;
  const replaySpans = isASpanReplay ? spansA : spansB;
  const replayTag = (isASpanReplay ? replaySpanA : replaySpanB)!;

  const flatFull = flattenDFS(fullSpans);
  const replayMain =
    replaySpans.find((s) => s.kind === "llm_call") ?? replaySpans[0];

  // Try to find the anchor span: first by span_id, then by matching inputs
  let anchorIdx = flatFull.findIndex((s) => s.span_id === replayTag);

  if (anchorIdx < 0 && replayMain) {
    const replayMsgs = JSON.stringify(
      (replayMain.inputs as Record<string, unknown> | null)?.messages,
    );
    if (replayMsgs) {
      anchorIdx = flatFull.findIndex(
        (s) =>
          s.kind === "llm_call" &&
          JSON.stringify(
            (s.inputs as Record<string, unknown> | null)?.messages,
          ) === replayMsgs,
      );
    }
  }

  const pairs: SpanPair[] = [];
  for (let i = 0; i < flatFull.length; i++) {
    const fSpan = flatFull[i];
    if (i === anchorIdx && replayMain) {
      const a = isASpanReplay ? replayMain : fSpan;
      const b = isASpanReplay ? fSpan : replayMain;
      pairs.push({
        spanA: a,
        spanB: b,
        kind: fSpan.kind,
        name: fSpan.name,
        status: deriveStatus(a, b),
      });
    } else {
      pairs.push({
        spanA: isASpanReplay ? null : fSpan,
        spanB: isASpanReplay ? fSpan : null,
        kind: fSpan.kind,
        name: fSpan.name,
        status: isASpanReplay ? "b-only" : "a-only",
      });
    }
  }

  // Remaining replay spans that weren't the anchor match
  const matchedReplayId = anchorIdx >= 0 ? replayMain?.span_id : null;
  for (const s of replaySpans) {
    if (s.span_id !== matchedReplayId) {
      pairs.push({
        spanA: isASpanReplay ? s : null,
        spanB: isASpanReplay ? null : s,
        kind: s.kind,
        name: s.name,
        status: isASpanReplay ? "a-only" : "b-only",
      });
    }
  }

  return pairs;
}
