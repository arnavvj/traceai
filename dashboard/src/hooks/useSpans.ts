import { useEffect, useState } from "react";
import { fetchSpans } from "../api/client";
import type { Span } from "../types/api";

interface UseSpansResult {
  spans: Span[];
  loading: boolean;
  error: string | null;
}

export function useSpans(traceId: string | null): UseSpansResult {
  const [spans, setSpans] = useState<Span[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!traceId) {
      setSpans([]);
      return;
    }
    setLoading(true);
    setError(null);
    fetchSpans(traceId)
      .then(setSpans)
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "Failed to load spans");
      })
      .finally(() => setLoading(false));
  }, [traceId]);

  return { spans, loading, error };
}
