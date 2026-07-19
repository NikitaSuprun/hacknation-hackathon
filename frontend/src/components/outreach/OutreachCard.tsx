import { cn } from "@/lib/utils";
import type { OutreachRow } from "@/lib/domain/types";
import { StatusChip } from "@/components/outreach/StatusChip";

/** "n days in state" from last_event_at — relative, mono. */
function daysInState(iso: string | null): string {
  if (!iso) return "";
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000);
  if (!Number.isFinite(days) || days <= 0) return "today";
  return `${days}d in state`;
}

export function OutreachCard({
  row,
  ventureName,
  flipChip,
  muted,
}: {
  row: OutreachRow;
  /** Resolved from the ranking rows by venture_id; falls back to to_email. */
  ventureName: string;
  /** True when this card's status changed since the previous render. */
  flipChip?: boolean;
  /** Closed column: 60% opacity. */
  muted?: boolean;
}) {
  const days = daysInState(row.last_event_at);
  return (
    <article data-demo-id={`outreach-card-${row.venture_id}`} className="animate-fade-up">
      <div className={cn("border border-line bg-paper p-3", muted && "opacity-60")}>
        <div className="flex items-baseline justify-between gap-2">
          <p className="truncate text-small font-medium text-ink">{ventureName}</p>
          {days && (
            <span className="shrink-0 font-mono text-[11px] tabular text-quiet">{days}</span>
          )}
        </div>
        <div className="mt-2">
          <StatusChip status={row.status} flip={flipChip} />
        </div>
        <p className="mt-2 truncate font-mono text-[11px] text-quiet">{row.to_email}</p>
        <p className="mt-1 truncate text-[13px] text-quiet">{row.subject}</p>
      </div>
    </article>
  );
}
