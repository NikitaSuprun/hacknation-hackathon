import {
  MEMO_SECTION_KEYS,
  type Memo,
  type VentureGap,
} from "@/lib/domain/types";
import { cn } from "@/lib/utils";

interface MergedGap {
  field: string;
  importance: number | null;
  question: string;
}

/**
 * gold.venture_gaps merged with memo bullets flagged missing:true (live mode
 * may return [] gaps, the memo still knows what's absent). Deduped by field,
 * sorted by importance descending, unknown importance last.
 */
export function mergeGaps(gaps: VentureGap[], memo?: Memo | null): MergedGap[] {
  const rows: MergedGap[] = gaps.map((g) => ({
    field: g.field,
    importance: g.importance,
    question: g.question_text,
  }));
  const seen = new Set(rows.map((r) => r.field));
  if (memo) {
    for (const key of MEMO_SECTION_KEYS) {
      for (const bullet of memo.sections[key]?.bullets ?? []) {
        if (!bullet.missing) continue;
        const field = bullet.gap_field ?? key;
        if (seen.has(field)) continue;
        seen.add(field);
        rows.push({ field, importance: null, question: bullet.text });
      }
    }
  }
  return rows.sort((a, b) => (b.importance ?? -1) - (a.importance ?? -1));
}

/** The missing-data panel: importance-sorted mono table of open gaps. */
export function MissingDataPanel({
  gaps,
  memo,
  className,
}: {
  gaps: VentureGap[];
  memo?: Memo | null;
  className?: string;
}) {
  const merged = mergeGaps(gaps, memo);
  return (
    <div data-demo-id="memo-gaps" className={className}>
      <p className="mono-label">Missing data</p>
      {merged.length === 0 ? (
        <p className="mt-2 max-w-measure-narrow text-small text-quiet">
          No open gaps. Every scored field is backed by a source.
        </p>
      ) : (
        <div className="mt-2">
          {merged.map((gap) => (
            <div key={gap.field} className="hairline-b py-2.5">
              <div className="flex items-baseline justify-between gap-3">
                <span className="break-all font-mono text-mono-data text-ink">{gap.field}</span>
                <span
                  className={cn(
                    "shrink-0 font-mono text-mono-data tabular",
                    gap.importance == null ? "text-quiet" : "text-ink",
                  )}
                >
                  {gap.importance == null ? "-" : gap.importance.toFixed(2)}
                </span>
              </div>
              <p className="mt-0.5 text-small text-quiet">{gap.question}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
