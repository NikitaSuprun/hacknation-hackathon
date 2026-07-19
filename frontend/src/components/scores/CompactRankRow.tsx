import { cn } from "@/lib/utils";
import { formatScore } from "@/lib/utils";

/**
 * Compact ranked row (rank · name · score) — the weights-page live preview
 * and any other place a dense re-rankable list is needed.
 */
export function CompactRankRow({
  rank,
  name,
  score,
  flash = false,
  muted = false,
  className,
}: {
  rank: number;
  name: string;
  score: number;
  /** Rank-change flash (240ms electric wash). */
  flash?: boolean;
  /** needs_more_data ventures render at reduced opacity. */
  muted?: boolean;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "hairline-b flex h-9 items-center gap-3 px-1 transition-colors duration-240 ease-swift",
        flash && "bg-electric-wash",
        muted && "opacity-60",
        className,
      )}
    >
      <span className="w-[3ch] shrink-0 font-mono text-mono-data tabular text-quiet">
        {String(rank).padStart(2, "0")}
      </span>
      <span className="min-w-0 flex-1 truncate text-small font-medium text-ink">{name}</span>
      <span className="shrink-0 font-mono text-mono-data tabular text-ink">
        {formatScore(score)}
      </span>
    </div>
  );
}
