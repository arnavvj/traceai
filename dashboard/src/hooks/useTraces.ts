import { useCallback, useEffect, useRef, useState } from "react";
import { fetchTraces } from "../api/client";
import type { Trace } from "../types/api";

const PAGE_SIZE = 25;
const POLL_INTERVAL_MS = 15_000;

interface UseTracesResult {
  traces: Trace[];
  loading: boolean;
  error: string | null;
  hasPending: boolean;
  applyPending: () => void;
  refresh: () => void;
  autoRefresh: boolean;
  setAutoRefresh: (v: boolean) => void;
}

export function useTraces(params: {
  offset: number;
  status: string | null;
  q: string;
}): UseTracesResult {
  const { offset, status, q } = params;

  const [traces, setTraces] = useState<Trace[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pendingTraces, setPendingTraces] = useState<Trace[] | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(true);

  const pendingRef = useRef<Trace[] | null>(null);
  pendingRef.current = pendingTraces;

  // Ref keeps the comparison in load() fresh — avoids stale closure bug
  // where traces captured at useCallback creation time is always [] on first poll.
  const tracesRef = useRef<Trace[]>([]);
  tracesRef.current = traces;

  // Signature used to detect changes during silent polling.
  const traceSignature = useCallback((ts: Trace[]) => ts.map((t) => `${t.trace_id}:${t.status}`).join(","), []);

  const load = useCallback(
    async (silent = false) => {
      if (!silent) setLoading(true);
      setError(null);
      try {
        const data = await fetchTraces({
          limit: PAGE_SIZE,
          offset,
          status: status || null,
          q: q || null,
        });
        if (silent) {
          // Only surface if data actually changed vs what's displayed.
          const current = traceSignature(tracesRef.current);
          const incoming = traceSignature(data.traces);
          if (current !== incoming) {
            setPendingTraces(data.traces);
          }
        } else {
          setTraces(data.traces);
          setPendingTraces(null);
        }
      } catch (err) {
        if (!silent) setError(err instanceof Error ? err.message : "Failed to load traces");
      } finally {
        if (!silent) setLoading(false);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [offset, status, q],
  );

  // Reload on param changes (not silent).
  useEffect(() => {
    void load(false);
  }, [load]);

  // Background poll.
  useEffect(() => {
    if (!autoRefresh) return;
    const id = setInterval(() => void load(true), POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [autoRefresh, load]);

  const applyPending = useCallback(() => {
    if (pendingRef.current) {
      setTraces(pendingRef.current);
      setPendingTraces(null);
    }
  }, []);

  const refresh = useCallback(() => void load(false), [load]);

  return {
    traces,
    loading,
    error,
    hasPending: pendingTraces !== null,
    applyPending,
    refresh,
    autoRefresh,
    setAutoRefresh,
  };
}

export { PAGE_SIZE };
