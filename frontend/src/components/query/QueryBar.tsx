/**
 * QueryBar — the ranked-pool query surface: one free-text prompt scored
 * semantically, plus structured chips (sector / location / score floor /
 * tier / status). Fully controlled; all state lives in the caller (or in
 * useVentureQuery). No dropdown libraries — chips and inputs only.
 */
import { useMemo, useState } from "react";
import type { RankedVenture, VentureStatus } from "@/lib/domain/types";
import {
  countActiveFilters,
  emptyQuery,
  locationOptionsOf,
  sectorOptionsOf,
  type TierFilter,
  type VentureQuery,
} from "@/lib/query";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { FilterChip } from "./FilterChip";

const SCORE_PRESETS = [50, 60, 70] as const;

const STATUS_OPTIONS: VentureStatus[] = [
  "sourced",
  "scored",
  "shortlisted",
  "outreach",
  "interviewing",
];

const TIER_OPTIONS: { value: TierFilter; label: string }[] = [
  { value: "scored", label: "scored" },
  { value: "needs_more_data", label: "needs data" },
  { value: "untiered", label: "untiered" },
];

/** Toggle membership of `item` in `list` (case-insensitive for strings). */
function toggle<T extends string>(list: T[], item: T): T[] {
  const lower = item.toLowerCase();
  return list.some((x) => x.toLowerCase() === lower)
    ? list.filter((x) => x.toLowerCase() !== lower)
    : [...list, item];
}

function has<T extends string>(list: T[], item: T): boolean {
  const lower = item.toLowerCase();
  return list.some((x) => x.toLowerCase() === lower);
}

function Group({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className="mono-label mr-0.5 shrink-0">{label}</span>
      {children}
    </div>
  );
}

export interface QueryBarProps {
  ventures: RankedVenture[];
  value: VentureQuery;
  onChange: (q: VentureQuery) => void;
  /** Optional "n of m match" readout rendered next to the SEMANTIC tag. */
  resultLabel?: string;
  className?: string;
}

export function QueryBar({ ventures, value, onChange, resultLabel, className }: QueryBarProps) {
  // Only tags that actually group ventures earn a chip — one-off technology
  // tags would read as sectors and bury the real ones.
  const sectors = useMemo(() => {
    const counts = new Map<string, number>();
    for (const venture of ventures) {
      for (const tag of venture.market_tags) {
        const key = tag.toLowerCase();
        counts.set(key, (counts.get(key) ?? 0) + 1);
      }
    }
    return sectorOptionsOf(ventures)
      .filter((tag) => (counts.get(tag.toLowerCase()) ?? 0) > 1)
      .slice(0, 8);
  }, [ventures]);
  const locations = useMemo(() => locationOptionsOf(ventures), [ventures]);
  const activeCount = countActiveFilters(value);
  const refined = value.tiers.length > 0 || value.statuses.length > 0;
  const [showMore, setShowMore] = useState(false);
  const moreOpen = showMore || refined;

  const patch = (p: Partial<VentureQuery>) => onChange({ ...value, ...p });

  return (
    <section
      aria-label="Query the ranked pool"
      data-demo-id="query-bar"
      className={cn("rounded-ctrl border border-line bg-paper", className)}
    >
      {/* Prompt row */}
      <div className="flex items-center gap-3 px-cell py-2.5">
        <Input
          data-demo-id="query-text"
          type="search"
          value={value.text}
          onChange={(e) => patch({ text: e.target.value })}
          aria-label="Describe what you're hunting"
          placeholder="Describe what you're hunting — e.g. 'tactile sensing for warehouse robots in Zurich'"
          className="h-9 flex-1 border-0 bg-transparent px-0 font-mono text-mono-data caret-electric focus-visible:ring-0 [&::-webkit-search-cancel-button]:appearance-none"
        />
        {resultLabel ? (
          <span className="mono-label tabular shrink-0 whitespace-nowrap" data-demo-id="query-count">
            {resultLabel}
          </span>
        ) : null}
        <span
          className={cn(
            "mono-label shrink-0 rounded-full border px-2 py-0.5 transition-colors duration-180 ease-swift",
            value.text.trim() ? "border-electric text-electric" : "border-line text-quiet",
          )}
        >
          semantic
        </span>
      </div>

      {/* Filter row */}
      <div className="flex flex-wrap items-center gap-x-gutter gap-y-2 border-t border-line px-cell py-2.5">
        {sectors.length > 0 ? (
          <Group label="Sector">
            {sectors.map((tag) => (
              <FilterChip
                key={tag}
                data-demo-id={`query-sector-${tag}`}
                active={has(value.sectors, tag)}
                onClick={() => patch({ sectors: toggle(value.sectors, tag) })}
              >
                {tag}
              </FilterChip>
            ))}
          </Group>
        ) : null}

        {locations.length > 0 ? (
          <Group label="Location">
            {locations.map((city) => (
              <FilterChip
                key={city}
                data-demo-id={`query-location-${city}`}
                active={has(value.locations, city)}
                onClick={() => patch({ locations: toggle(value.locations, city) })}
              >
                {city}
              </FilterChip>
            ))}
          </Group>
        ) : null}

        <Group label="Score">
          {SCORE_PRESETS.map((n) => (
            <FilterChip
              key={n}
              data-demo-id={`query-minscore-${n}`}
              active={value.minScore === n}
              onClick={() => patch({ minScore: value.minScore === n ? null : n })}
              className="tabular"
            >
              {n}+
            </FilterChip>
          ))}
          <input
            data-demo-id="query-minscore"
            type="number"
            inputMode="numeric"
            min={0}
            max={100}
            step={1}
            aria-label="Minimum score"
            placeholder="min"
            value={value.minScore ?? ""}
            onChange={(e) => {
              const raw = e.target.value.trim();
              const n = Number(raw);
              patch({ minScore: raw === "" || Number.isNaN(n) ? null : n });
            }}
            className="tabular h-6 w-14 rounded-ctrl border border-line bg-paper px-1.5 font-mono text-mono-label text-ink transition-colors duration-120 ease-swift placeholder:text-quiet focus-visible:border-electric focus-visible:outline-none"
          />
        </Group>

        {!moreOpen && (
          <button
            type="button"
            data-demo-id="query-more"
            onClick={() => setShowMore(true)}
            className="mono-label transition-colors duration-120 ease-swift hover:text-ink"
          >
            + tier · status
          </button>
        )}

        {moreOpen && (
          <>
            <Group label="Tier">
              {TIER_OPTIONS.map((t) => (
                <FilterChip
                  key={t.value}
                  data-demo-id={`query-tier-${t.value}`}
                  active={value.tiers.includes(t.value)}
                  onClick={() => patch({ tiers: toggle(value.tiers, t.value) })}
                >
                  {t.label}
                </FilterChip>
              ))}
            </Group>

            <Group label="Status">
              {STATUS_OPTIONS.map((s) => (
                <FilterChip
                  key={s}
                  data-demo-id={`query-status-${s}`}
                  active={value.statuses.includes(s)}
                  onClick={() => patch({ statuses: toggle(value.statuses, s) })}
                >
                  {s}
                </FilterChip>
              ))}
            </Group>
          </>
        )}

        {activeCount > 0 ? (
          <button
            type="button"
            data-demo-id="query-clear"
            onClick={() => onChange(emptyQuery())}
            className="ml-auto inline-flex items-center gap-2 rounded-ctrl px-2 py-1 font-mono text-mono-label uppercase text-quiet transition-colors duration-120 ease-swift hover:bg-wash hover:text-ink focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
          >
            <span className="tabular">
              {activeCount} filter{activeCount === 1 ? "" : "s"}
            </span>
            <span aria-hidden="true">·</span>
            clear
          </button>
        ) : null}
      </div>
    </section>
  );
}
