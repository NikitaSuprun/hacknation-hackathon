import { useState } from "react";
import { EvidenceChip } from "@/components/memo/EvidenceChip";
import { Badge } from "@/components/ui/badge";
import {
  CATEGORY_KEYS,
  CATEGORY_LABELS,
  type CategoryKey,
  type ScoreBreakdown,
} from "@/lib/domain/types";
import { cn, formatPercent, formatScore } from "@/lib/utils";

/** A capped score is one whose breakdown rationale names the cap. */
function isCapped(rationale: string | null | undefined): boolean {
  return rationale != null && /\bcap(?:ped|s)?\b/i.test(rationale);
}

/**
 * The 9-category score breakdown: mono label · 8px ink bar · mono score.
 * N/A categories render a dashed track with "weight redistributed"; capped
 * scores carry a hairline tick at the cap. Rows expand to rationale + sources.
 */
export function CategoryBreakdown({
  scores,
  breakdown,
  className,
}: {
  scores: Record<CategoryKey, number | null>;
  breakdown?: ScoreBreakdown;
  className?: string;
}) {
  const [openKeys, setOpenKeys] = useState<Set<CategoryKey>>(() => new Set());
  const toggle = (key: CategoryKey) => {
    setOpenKeys((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  return (
    <div className={className}>
      {CATEGORY_KEYS.map((key) => {
        const score = scores[key];
        const cat = breakdown?.categories[key];
        const capped = score != null && isCapped(cat?.rationale);
        const open = openKeys.has(key);
        return (
          <div key={key} className="hairline-b">
            <button
              type="button"
              onClick={() => toggle(key)}
              aria-expanded={open}
              className="grid w-full grid-cols-[minmax(9rem,13rem)_minmax(0,1fr)_auto] items-center gap-x-4 py-3 text-left transition-colors duration-120 ease-swift hover:bg-wash"
            >
              <span className="mono-label truncate">{CATEGORY_LABELS[key]}</span>
              {score == null ? (
                <div className="h-2 w-full border border-dashed border-line bg-transparent" />
              ) : (
                <div className="relative h-2 w-full bg-wash">
                  <div
                    className="h-full w-full origin-left bg-ink transition-transform duration-240 ease-swift"
                    style={{ transform: `scaleX(${Math.max(0, Math.min(100, score)) / 100})` }}
                  />
                  {capped && (
                    <span
                      className="absolute -top-1 h-4 w-px bg-ink"
                      style={{ left: `${Math.max(0, Math.min(100, score))}%` }}
                      title="Score capped, see rationale"
                    />
                  )}
                </div>
              )}
              <span
                className={cn(
                  "whitespace-nowrap text-right font-mono text-mono-data tabular",
                  score == null ? "text-quiet" : "text-ink",
                )}
              >
                {score == null ? "N/A, weight redistributed" : formatScore(score)}
              </span>
            </button>
            {open && (
              <div className="animate-fade-in pb-4 pl-0 pr-4 md:pl-[calc(13rem+1rem)]">
                {cat ? (
                  <>
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant="quiet">{cat.method}</Badge>
                      {cat.confidence != null && (
                        <span className="font-mono text-[11px] text-quiet">
                          confidence {formatPercent(cat.confidence)}
                        </span>
                      )}
                      {capped && (
                        <span className="font-mono text-[11px] uppercase tracking-[0.06em] text-quiet">
                          capped
                        </span>
                      )}
                      <EvidenceChip evidence={cat.evidence ?? []} />
                    </div>
                    {cat.rationale && (
                      <p className="mt-2 max-w-measure text-small text-quiet">{cat.rationale}</p>
                    )}
                  </>
                ) : (
                  <p className="max-w-measure text-small text-quiet">
                    No breakdown recorded for this category.
                  </p>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
