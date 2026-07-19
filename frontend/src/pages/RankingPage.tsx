import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { Skeleton } from "@/components/ui/skeleton";
import { dataSource } from "@/lib/data";
import { formatScore } from "@/lib/utils";

/**
 * TODO(Track B): full ranked list — score/confidence bars, status chips,
 * funding badges, quality tiers, needs_more_data treatment, select-for-outreach.
 */
export default function RankingPage() {
  const { thesisId = "" } = useParams();
  const ds = dataSource();
  const { data: ventures, isLoading } = useQuery({
    queryKey: ["ranking", thesisId],
    queryFn: () => ds.getRanking(thesisId),
  });

  return (
    <div className="py-gutter-lg">
      <p className="mono-label mb-2">Ranked ventures</p>
      <h1 className="font-display text-h1">Ranking</h1>
      <div className="mt-8">
        {isLoading &&
          Array.from({ length: 6 }, (_, i) => <Skeleton key={i} className="mb-px h-14 w-full" />)}
        {ventures?.map((venture, index) => (
          <Link
            key={venture.venture_id}
            to={`/t/${thesisId}/venture/${venture.venture_id}`}
            className="hairline-b flex h-14 items-center gap-6 px-2 transition-colors duration-120 ease-swift hover:bg-wash"
          >
            <span className="w-8 font-mono text-mono-data tabular text-quiet">
              {String(index + 1).padStart(2, "0")}
            </span>
            <span className="flex-1 truncate">
              <span className="font-medium text-ink">{venture.name}</span>
              <span className="ml-3 text-small text-quiet">{venture.one_liner}</span>
            </span>
            <span className="font-mono text-mono-data tabular text-ink">
              {formatScore(venture.final_score)}
            </span>
          </Link>
        ))}
      </div>
    </div>
  );
}
