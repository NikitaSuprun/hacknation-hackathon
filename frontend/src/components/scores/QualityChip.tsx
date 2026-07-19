import { Badge } from "@/components/ui/badge";
import type { QualityTier } from "@/lib/domain/types";

/**
 * Quality-tier chip: dashed for needs_more_data, quiet "unscored tier" for
 * null (fresh signals the pipeline hasn't tiered). Fully scored ventures show
 * nothing, the score column already carries that information.
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
      <Badge variant="dashed" className={className} title="Not enough signal to score this venture">
        needs data
      </Badge>
    );
  }
  if (tier === null) {
    return (
      <Badge variant="quiet" className={className} title="The pipeline has not tiered this venture yet">
        untiered
      </Badge>
    );
  }
  return null;
}
