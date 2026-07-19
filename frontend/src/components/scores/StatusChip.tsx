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

/**
 * Resting states (sourced/scored) are the norm — they drop the pill outline
 * and sit as quiet mono text, so a venture that is actually in flight reads
 * instantly against them.
 */
const RESTING: VentureStatus[] = ["sourced", "scored"];

export function StatusChip({
  status,
  className,
}: {
  status: VentureStatus;
  className?: string;
}) {
  const resting = RESTING.includes(status);
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 whitespace-nowrap rounded-full py-0.5 font-mono text-[11px] uppercase leading-4 tracking-[0.06em]",
        resting ? "text-quiet" : "border border-line-strong px-2.5 text-ink",
        className,
      )}
    >
      <span className={cn("h-1.5 w-1.5 shrink-0 rounded-full", DOT[status])} />
      {status}
    </span>
  );
}
