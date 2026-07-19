import { Link } from "react-router-dom";
import type { RankedVenture } from "@/lib/domain/types";
import { formatScore } from "@/lib/utils";

/** Compact ranked-venture card, the pool you would send outreach to next. */
export function ShortlistCard({
  venture,
  thesisId,
}: {
  venture: RankedVenture;
  thesisId: string;
}) {
  return (
    <Link
      to={`/t/${thesisId}/venture/${venture.venture_id}`}
      className="block border border-line bg-paper p-3 transition-colors duration-120 ease-swift hover:border-line-strong hover:bg-wash"
    >
      <div className="flex items-baseline justify-between gap-2">
        <p className="truncate text-small font-medium text-ink">{venture.name}</p>
        <span className="shrink-0 font-mono text-mono-data tabular text-ink">
          {formatScore(venture.final_score)}
        </span>
      </div>
      <p className="mt-1 truncate text-[13px] text-quiet">{venture.one_liner}</p>
      <span className="mt-2 inline-flex items-center rounded-full border border-line px-2 py-px font-mono text-[11px] uppercase leading-4 tracking-[0.06em] text-quiet">
        {venture.status}
      </span>
    </Link>
  );
}
