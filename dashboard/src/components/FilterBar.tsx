import { useEffect, useRef, useState } from "react";

interface Props {
  status: string | null;
  onStatusChange: (v: string | null) => void;
  onSearchChange: (v: string) => void;
  onRefresh: () => void;
  autoRefresh: boolean;
  onAutoRefreshChange: (v: boolean) => void;
}

export function FilterBar({
  status,
  onStatusChange,
  onSearchChange,
  onRefresh,
  autoRefresh,
  onAutoRefreshChange,
}: Props) {
  const [rawSearch, setRawSearch] = useState("");
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      onSearchChange(rawSearch);
    }, 300);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [rawSearch, onSearchChange]);

  return (
    <div className="flex items-center gap-2 border-b border-border bg-sidebar px-3 py-2">
      <select
        value={status ?? ""}
        onChange={(e) => onStatusChange(e.target.value || null)}
        className="rounded border border-border bg-panel px-2 py-1 text-xs text-text-primary focus:outline-none focus:ring-1 focus:ring-accent"
      >
        <option value="">All statuses</option>
        <option value="ok">OK</option>
        <option value="error">Error</option>
        <option value="pending">Pending</option>
        <option value="timeout">Timeout</option>
      </select>

      <input
        type="text"
        placeholder="Search traces…"
        value={rawSearch}
        onChange={(e) => setRawSearch(e.target.value)}
        className="min-w-0 flex-1 rounded border border-border bg-panel px-2 py-1 text-xs text-text-primary placeholder-text-muted focus:outline-none focus:ring-1 focus:ring-accent"
      />

      <button
        onClick={onRefresh}
        title="Refresh"
        className="rounded border border-border bg-panel px-2 py-1 text-xs text-text-secondary hover:bg-border"
      >
        ↺
      </button>

      <button
        onClick={() => onAutoRefreshChange(!autoRefresh)}
        title={autoRefresh ? "Disable auto-refresh" : "Enable auto-refresh"}
        className={`rounded border px-2 py-1 text-xs transition-colors ${autoRefresh ? "border-accent bg-accent/20 text-accent" : "border-border bg-panel text-text-muted"}`}
      >
        Auto
      </button>
    </div>
  );
}
