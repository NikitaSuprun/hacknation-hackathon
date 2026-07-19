import { Badge } from "@/components/ui/badge";
import type { FundingSignal } from "@/lib/domain/types";

/**
 * The unfunded-signal badge from gold.candidate_pool.funding_signal.
 * Renders nothing when the pool carries no signal for the venture.
 */
export function FundingBadge({
  signal,
  className,
}: {
  signal: FundingSignal | null;
  className?: string;
}) {
  if (!signal) return null;
  if (signal === "none_found") {
    return (
      <Badge variant="quiet" className={className}>
        no prior VC · heuristic
      </Badge>
    );
  }
  if (signal === "suspected") {
    return (
      <Badge variant="dashed" className={className}>
        funding suspected
      </Badge>
    );
  }
  return (
    <Badge variant="outline" className={className}>
      no prior VC · confirmed
    </Badge>
  );
}
