import type { SpanStatus } from "../types/api";

const STATUS_STYLES: Record<SpanStatus, string> = {
  ok: "bg-green-100 text-green-700 border border-green-300 dark:bg-green-900/50 dark:text-green-400 dark:border-green-800",
  error: "bg-red-100 text-red-700 border border-red-300 dark:bg-red-900/50 dark:text-red-400 dark:border-red-800",
  pending: "bg-orange-100 text-orange-700 border border-orange-300 dark:bg-orange-900/50 dark:text-orange-400 dark:border-orange-800",
  timeout: "bg-orange-100 text-orange-700 border border-orange-300 dark:bg-orange-900/50 dark:text-orange-400 dark:border-orange-800",
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
