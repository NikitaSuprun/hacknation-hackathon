import { EvidenceChip } from "@/components/memo/EvidenceChip";
import {
  MEMO_SECTION_LABELS,
  type MemoBullet,
  type MemoMarketSection,
  type MemoSection,
  type MemoSectionKey,
} from "@/lib/domain/types";
import { cn } from "@/lib/utils";

function isInterviewCited(bullet: MemoBullet): boolean {
  return (bullet.evidence ?? []).some((e) => e.source_type === "interview");
}

function MarketFigures({ section }: { section: MemoMarketSection }) {
  const rows = (
    [
      ["TAM", section.tam],
      ["SAM", section.sam],
      ["SOM", section.som],
    ] as [string, string | null | undefined][]
  ).filter((r): r is [string, string] => r[1] != null && r[1] !== "");
  if (rows.length === 0) return null;
  return (
    <dl className="mt-3 max-w-measure">
      {rows.map(([label, value]) => (
        <div key={label} className="hairline-b flex items-baseline justify-between gap-4 py-1.5">
          <dt className="mono-label">{label}</dt>
          <dd className="font-mono text-mono-data tabular text-ink">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

/**
 * One memo section: eyebrow label, bullets at reading measure. Bullets flagged
 * missing render as gaps (dashed left rule, quiet, "missing — asked in
 * interview"); interview-cited bullets get the consented electric-wash tint.
 */
export function MemoSectionView({
  sectionKey,
  section,
  className,
}: {
  sectionKey: MemoSectionKey;
  section: MemoSection | MemoMarketSection;
  className?: string;
}) {
  const bullets = section.bullets ?? [];
  return (
    <section className={className}>
      <p className="mono-label">{MEMO_SECTION_LABELS[sectionKey]}</p>
      {bullets.length === 0 ? (
        <p className="mt-2 max-w-measure text-small text-quiet">Nothing recorded yet.</p>
      ) : (
        <ul className="mt-2 max-w-measure space-y-2">
          {bullets.map((bullet, i) => {
            const consented = isInterviewCited(bullet);
            return (
              <li
                key={i}
                className={cn(
                  "text-body",
                  bullet.missing &&
                    "border-l border-dashed border-line-strong pl-3 text-quiet",
                  consented && "bg-electric-wash px-2 py-1",
                )}
              >
                <span>{bullet.text}</span>
                {bullet.evidence && bullet.evidence.length > 0 && (
                  <EvidenceChip evidence={bullet.evidence} className="ml-2 align-middle" />
                )}
                {bullet.missing && (
                  <span className="ml-2 whitespace-nowrap font-mono text-[11px] uppercase tracking-[0.06em] text-quiet">
                    missing — asked in interview
                  </span>
                )}
                {consented && (
                  <span className="ml-2 whitespace-nowrap font-mono text-[11px] uppercase tracking-[0.06em] text-quiet">
                    consented
                  </span>
                )}
              </li>
            );
          })}
        </ul>
      )}
      {sectionKey === "market_tam_sam_som" && (
        <MarketFigures section={section as MemoMarketSection} />
      )}
    </section>
  );
}
