import { useState } from "react";

const COLLAPSE_THRESHOLD = 1000;

interface Props {
  data: Record<string, unknown> | null;
  label: string;
}

export function JsonViewer({ data, label }: Props) {
  const [expanded, setExpanded] = useState(false);

  if (!data) return null;

  const json = JSON.stringify(data, null, 2);
  const isLong = json.length > COLLAPSE_THRESHOLD;
  const displayed = isLong && !expanded ? json.slice(0, COLLAPSE_THRESHOLD) + "\n…" : json;

  return (
    <div className="mb-3">
      <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-text-muted">{label}</div>
      <pre className="whitespace-pre-wrap break-all rounded bg-background p-3 text-xs leading-relaxed text-text-primary">
        {displayed}
      </pre>
      {isLong && (
        <button
          onClick={() => setExpanded((v) => !v)}
          className="mt-1 text-xs text-accent hover:underline"
        >
          {expanded ? "Show less" : "Show more"}
        </button>
      )}
    </div>
  );
}
