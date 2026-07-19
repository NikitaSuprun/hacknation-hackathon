import type { VentureStatus } from "@/lib/domain/types";
import { cn } from "@/lib/utils";

/**
 * Outlined status pill: mono 11px uppercase with a 6px state dot.
 * Dot color encodes the machine state — electric only while a decision is in
 * flight (outreach/interviewing), quiet for pre-decision, ink for terminal.
 */
const DOT: Record<VentureStatus, string> = {
  sourced: "bg-quiet",
  scored: "bg-quiet",
  shortlisted: "bg-quiet",
  outreach: "bg-electric",
  interviewing: "bg-electric",
  passed: "bg-ink",
  archived: "bg-ink",
};

export function StatusChip({
  status,
  className,
}: {
  status: VentureStatus;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border border-line-strong px-2.5 py-0.5 font-mono text-[11px] uppercase leading-4 tracking-[0.06em] text-ink",
        className,
      )}
    >
      <span className={cn("h-1.5 w-1.5 shrink-0 rounded-full", DOT[status])} />
      {status}
    </span>
  );
}
