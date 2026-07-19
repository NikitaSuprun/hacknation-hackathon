/**
 * Stage 2 of thesis intake — a scripted, deterministic extraction pass.
 * Field rows fade up one by one (150 ms apart), each resolving to
 * "extracted" or "not found" against the store's missingFields; the whole
 * pass hands off to review at 1.6 s. A click anywhere on the card skips.
 */
import { useEffect, useState } from "react";
import { Card } from "@/components/ui/card";

interface ExtractRow {
  label: string;
  fields: string[];
}

const EXTRACT_ROWS: ExtractRow[] = [
  { label: "Name", fields: ["name"] },
  { label: "Sectors", fields: ["sectors"] },
  { label: "Geographies", fields: ["geographies"] },
  { label: "Stages", fields: ["stages"] },
  { label: "Team size", fields: ["min_team", "max_team"] },
  { label: "Check size", fields: ["check_size_min_chf", "check_size_max_chf"] },
  { label: "Policies", fields: ["require_no_prior_vc", "exclude_corporate_oss"] },
  { label: "Notes", fields: ["notes"] },
];

/** Row reveal cadence and total pass duration (ms). */
export const EXTRACT_ROW_INTERVAL_MS = 150;
export const EXTRACT_TOTAL_MS = 1600;

export function ExtractingStage({
  source,
  missingFields,
  onDone,
}: {
  source: string;
  missingFields: string[];
  onDone: () => void;
}) {
  const [shown, setShown] = useState(0);

  useEffect(() => {
    const reveal = window.setInterval(
      () => setShown((s) => Math.min(s + 1, EXTRACT_ROWS.length)),
      EXTRACT_ROW_INTERVAL_MS,
    );
    const done = window.setTimeout(onDone, EXTRACT_TOTAL_MS);
    return () => {
      window.clearInterval(reveal);
      window.clearTimeout(done);
    };
  }, [onDone]);

  const missing = new Set(missingFields);

  return (
    <div className="mx-auto max-w-[640px]">
      <p className="mono-label mb-2">Investment thesis</p>
      <h1 className="font-display text-h1">Reading it now.</h1>

      <Card className="mt-8">
        {/* The whole card is a skip control — one click jumps to review. */}
        <button
          type="button"
          data-demo-id="thesis-extracting"
          onClick={onDone}
          className="block w-full cursor-pointer p-6 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          aria-label="Skip extraction"
        >
          <p className="animate-fade-in font-mono text-mono-data text-quiet">
            Reading {source}
          </p>
          <div className="mt-4 min-h-[272px]">
            {EXTRACT_ROWS.slice(0, shown).map((row) => {
              const notFound = row.fields.some((f) => missing.has(f));
              return (
                <div
                  key={row.label}
                  className="flex animate-fade-up items-baseline justify-between py-1.5"
                >
                  <span className="text-small text-ink">{row.label}</span>
                  {notFound ? (
                    <span className="font-mono text-mono-label text-danger">not found</span>
                  ) : (
                    <span className="font-mono text-mono-label text-quiet">extracted</span>
                  )}
                </div>
              );
            })}
          </div>
        </button>
      </Card>
    </div>
  );
}
