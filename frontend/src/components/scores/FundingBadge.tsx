import { Badge } from "@/components/ui/badge";
import type { FundingSignal } from "@/lib/domain/types";

/**
 * The unfunded-signal badge from gold.candidate_pool.funding_signal.
 *
 * The thesis requires no prior VC, so `none_found` is the expected case —
 * in dense contexts (the ranked list) it stays silent so the anomalies read
 * as anomalies. Detail views pass `dense={false}` to state it explicitly.
 */
export function FundingBadge({
  signal,
  className,
  dense = true,
}: {
  signal: FundingSignal | null;
  className?: string;
  dense?: boolean;
}) {
  if (!signal) return null;
  if (signal === "suspected") {
    return (
      <Badge variant="dashed" className={className} title="Funding suspected — not confirmed in any registry">
        {dense ? "suspected" : "funding suspected"}
      </Badge>
    );
  }
  if (signal === "confirmed_none") {
    return (
      <Badge variant="outline" className={className} title="No prior VC — confirmed in interview">
        {dense ? "VC-free" : "no prior VC · confirmed"}
      </Badge>
    );
  }
  if (dense) return null;
  return (
    <Badge variant="quiet" className={className}>
      no prior VC · heuristic
    </Badge>
  );
}
