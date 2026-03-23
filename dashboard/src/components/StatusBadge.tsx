import type { SpanStatus } from "../types/api";

const STATUS_STYLES: Record<SpanStatus, string> = {
  ok: "bg-green-900/50 text-green-400 border border-green-800",
  error: "bg-red-900/50 text-red-400 border border-red-800",
  pending: "bg-orange-900/50 text-orange-400 border border-orange-800",
  timeout: "bg-orange-900/50 text-orange-400 border border-orange-800",
};

interface Props {
  status: SpanStatus;
}

export function StatusBadge({ status }: Props) {
  return (
    <span className={`inline-block rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide ${STATUS_STYLES[status]}`}>
      {status}
    </span>
  );
}
