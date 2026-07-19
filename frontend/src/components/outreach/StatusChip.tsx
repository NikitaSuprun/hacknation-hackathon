import { cn } from "@/lib/utils";
import type { OutreachStatus } from "@/lib/domain/types";

/**
 * Outlined mono status pill with a 6px state dot.
 * Dot vocabulary: electric = live pipeline motion (sent onward), quiet = not
 * yet in flight, danger = a dead end, ink = closed out.
 */
const DOT_CLASS: Record<OutreachStatus, string> = {
  draft: "bg-quiet",
  approved: "bg-quiet",
  sent: "bg-electric",
  replied: "bg-electric",
  bounced: "bg-danger",
  consented: "bg-electric",
  declined: "bg-danger",
  interview_scheduled: "bg-electric",
  interview_started: "bg-electric",
  interviewed: "bg-electric",
  closed: "bg-ink",
  opted_out: "bg-danger",
  expired: "bg-danger",
};

export function StatusChip({ status, flip }: { status: OutreachStatus; flip?: boolean }) {
  return (
    <span
      // Keyed by status so a state change remounts the chip and replays the flip.
      key={status}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border border-line-strong px-2 py-px font-mono text-[11px] uppercase leading-4 tracking-[0.06em] text-ink",
        flip && "outreach-chip-flip",
      )}
    >
      <span aria-hidden className={cn("h-1.5 w-1.5 shrink-0 rounded-full", DOT_CLASS[status])} />
      {status.replace(/_/g, " ")}
    </span>
  );
}
