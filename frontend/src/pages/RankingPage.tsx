import { useMemo } from "react";
import { Link, useParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ConfidenceBar } from "@/components/scores/ConfidenceBar";
import { FundingBadge } from "@/components/scores/FundingBadge";
import { QualityChip } from "@/components/scores/QualityChip";
import { ScoreBar } from "@/components/scores/ScoreBar";
import { StatusChip } from "@/components/scores/StatusChip";
import {
  COLD_START_HINT,
  useColdStartHint,
  useFlashOnReorder,
  useRanking,
} from "@/hooks/useInvestorData";
import { QueryBar, RelevanceTag, useVentureQuery } from "@/components/query";
import { cn, formatScore } from "@/lib/utils";

/** Shared column template so the mono-label header stays aligned with rows. */
const ROW_GRID =
  "grid grid-cols-[2.5rem_minmax(0,1fr)_7.5rem] items-center gap-x-4 px-2 lg:grid-cols-[2.5rem_minmax(0,1fr)_7rem_7rem_7.5rem_7.5rem_7.5rem]";

function SkeletonRow() {
  return (
    <div className={cn(ROW_GRID, "hairline-b h-14")}>
      <Skeleton className="h-3 w-6" />
      <div className="min-w-0">
        <Skeleton className="h-4 w-3/5 max-w-64" />
      </div>
      <Skeleton className="hidden h-5 w-24 rounded-full lg:block" />
      <Skeleton className="hidden h-5 w-20 rounded-full lg:block" />
      <Skeleton className="hidden h-5 w-20 rounded-full lg:block" />
      <span className="hidden lg:block" />
      <div className="space-y-1.5">
        <Skeleton className="ml-auto h-3 w-10" />
        <Skeleton className="h-1 w-full" />
        <Skeleton className="h-0.5 w-full" />
      </div>
    </div>
  );
}

/**
 * The flagship ranked list: 56px hairline rows over gold.v_ranked_ventures,
 * already sorted by the seam under the active weights. Order changes flash
 * the moved rows for 240ms (FLIP-lite).
 */
export default function RankingPage() {
  const { thesisId = "" } = useParams();
  const { data: ventures, isLoading, isError, error, refetch } = useRanking(thesisId);
  const coldStart = useColdStartHint(isLoading);

  // The query bar filters and (with a prompt) relevance-ranks the pool
  // client-side; with no query it passes the seam's ranking through untouched.
  const pool = useMemo(() => ventures ?? [], [ventures]);
  const { query, setQuery, hits, activeCount } = useVentureQuery(pool);
  const rows = useMemo(() => hits.map((hit) => hit.venture), [hits]);
  const hitByVenture = useMemo(
    () => new Map(hits.map((hit) => [hit.venture.venture_id, hit])),
    [hits],
  );

  const ids = useMemo(() => rows.map((v) => v.venture_id), [rows]);
  const flashed = useFlashOnReorder(ids);

  const resultLabel =
    activeCount > 0
      ? `${hits.length} of ${pool.length} match`
      : `${String(pool.length).padStart(2, "0")} ventures · ranked under active weights`;

  return (
    <div className="py-gutter-lg">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="mono-label mb-2">Ranked ventures</p>
          <h1 className="font-display text-h1">Ranking</h1>
        </div>
        {pool.length > 0 && (
          <p className="font-mono text-mono-data tabular text-quiet">{resultLabel}</p>
        )}
      </div>

      {pool.length > 0 && (
        <QueryBar
          className="mt-8"
          ventures={pool}
          value={query}
          onChange={setQuery}
          resultLabel={activeCount > 0 ? `${hits.length} of ${pool.length}` : undefined}
        />
      )}

      <div className="mt-8">
        <div className={cn(ROW_GRID, "h-9 border-b border-line-strong")}>
          <span className="mono-label">Rank</span>
          <span className="mono-label">Venture</span>
          <span className="mono-label hidden lg:block">Funding</span>
          <span className="mono-label hidden lg:block">Quality</span>
          <span className="mono-label hidden lg:block">Status</span>
          <span className="hidden lg:block" />
          <span className="mono-label text-right">Score</span>
        </div>

        {isLoading && (
          <>
            {Array.from({ length: 8 }, (_, i) => (
              <SkeletonRow key={i} />
            ))}
            {coldStart && (
              <p className="mt-4 font-mono text-mono-data text-quiet">{COLD_START_HINT}</p>
            )}
          </>
        )}

        {isError && (
          <div className="max-w-measure-narrow py-gutter">
            <p className="mono-label mb-2">Ranking unavailable</p>
            <p className="text-body text-quiet">
              The ranking query failed{error instanceof Error ? ` — ${error.message}` : ""}.
            </p>
            <Button variant="outline" size="sm" className="mt-4" onClick={() => refetch()}>
              Retry
            </Button>
          </div>
        )}

        {ventures && ventures.length === 0 && (
          <div className="max-w-measure-narrow py-gutter">
            <p className="mono-label mb-2">Empty pool</p>
            <p className="text-body text-quiet">No ventures match the active thesis yet.</p>
            <Button asChild variant="outline" size="sm" className="mt-4">
              <Link to="/thesis">Review thesis</Link>
            </Button>
          </div>
        )}

        {pool.length > 0 && rows.length === 0 && (
          <div className="max-w-measure-narrow py-gutter">
            <p className="mono-label mb-2">Nothing matches</p>
            <p className="text-body text-quiet">
              No venture in the pool matches that query. Loosen a filter or reword the prompt.
            </p>
          </div>
        )}

        {rows.map((venture, index) => {
          const needsMore = venture.quality_tier === "needs_more_data";
          const isFlashed = flashed.has(venture.venture_id);
          const hit = hitByVenture.get(venture.venture_id);
          return (
            <Link
              key={venture.venture_id}
              to={`/t/${thesisId}/venture/${venture.venture_id}`}
              data-demo-id={`venture-row-${venture.venture_id}`}
              className={cn(
                ROW_GRID,
                "group hairline-b transition-colors duration-240 ease-swift hover:bg-wash",
                hit?.relevance == null ? "h-14" : "min-h-14 py-2",
                isFlashed && "bg-electric-wash",
              )}
            >
              <span className="font-mono text-mono-data tabular text-quiet">
                {String(index + 1).padStart(2, "0")}
              </span>
              <span className="min-w-0">
                <span className="block truncate">
                  <span className="text-body font-medium text-ink">{venture.name}</span>
                  {/* A three-letter stub of the descriptor is noise — drop it on narrow screens. */}
                  <span className="ml-3 hidden text-small text-quiet sm:inline">
                    {venture.one_liner}
                  </span>
                </span>
                {hit && <RelevanceTag hit={hit} />}
              </span>
              <span className="hidden lg:block">
                <FundingBadge signal={venture.funding_signal} />
              </span>
              <span className="hidden lg:block">
                <QualityChip tier={venture.quality_tier} />
              </span>
              <span className="hidden lg:block">
                <StatusChip status={venture.status} />
              </span>
              <span className="hidden text-right lg:block">
                {needsMore ? (
                  <span
                    className="block font-mono text-[11px] leading-tight text-quiet"
                    title="Not enough signal to choose"
                  >
                    Not enough signal to choose
                  </span>
                ) : (
                  <span className="font-mono text-[11px] uppercase tracking-[0.06em] text-quiet opacity-0 transition-opacity duration-120 ease-swift group-hover:opacity-100">
                    open →
                  </span>
                )}
              </span>
              <span className={cn("block space-y-1", needsMore && "opacity-60")}>
                <span className="block text-right font-mono text-mono-data tabular text-ink">
                  {formatScore(venture.final_score)}
                </span>
                <ScoreBar value={venture.final_score} flash={isFlashed} />
                <ConfidenceBar value={venture.confidence} />
              </span>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
