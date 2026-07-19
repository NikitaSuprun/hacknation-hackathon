import { Badge } from "@/components/ui/badge";
import type { QualityTier } from "@/lib/domain/types";

/**
 * Quality-tier chip: dashed for needs_more_data, quiet "unscored tier" for
 * null (fresh signals the pipeline hasn't tiered). Fully scored ventures show
 * nothing — the score column already carries that information.
 */
export function QualityChip({
  tier,
  className,
}: {
  tier: QualityTier | null;
  className?: string;
}) {
  if (tier === "needs_more_data") {
    return (
      <Badge variant="dashed" className={className}>
        needs more data
      </Badge>
    );
  }
  if (tier === null) {
    return (
      <Badge variant="quiet" className={className}>
        unscored tier
      </Badge>
    );
  }
  return null;
}
