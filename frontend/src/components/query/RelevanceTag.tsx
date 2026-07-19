/**
 * Relevance readout for a ranking row: a mono "match 0.82" tag plus up to two
 * matched-snippet lines with the matched tokens marked. Rendered by the
 * ranking rows; returns null when the query has no text (relevance === null).
 */
import type { MatchedSnippet, QueryHit } from "@/lib/query";
import { cn } from "@/lib/utils";

const FIELD_LABELS: Record<string, string> = {
  name: "name",
  tags: "tags",
  one_liner: "summary",
};

function fieldLabel(field: string): string {
  if (FIELD_LABELS[field]) return FIELD_LABELS[field];
  const [kind, category] = field.split(":");
  const readable = (category ?? "").replace(/_/g, " ");
  return kind === "evidence" ? `evidence · ${readable}` : readable;
}

/** Split a snippet into plain / marked segments using the precomputed ranges. */
function segmentsOf(snippet: MatchedSnippet): { text: string; marked: boolean }[] {
  const out: { text: string; marked: boolean }[] = [];
  let cursor = 0;
  const ranges = [...snippet.ranges].sort((a, b) => a[0] - b[0]);
  for (const [start, end] of ranges) {
    if (start < cursor || start >= end || end > snippet.snippet.length) continue;
    if (start > cursor) out.push({ text: snippet.snippet.slice(cursor, start), marked: false });
    out.push({ text: snippet.snippet.slice(start, end), marked: true });
    cursor = end;
  }
  if (cursor < snippet.snippet.length) {
    out.push({ text: snippet.snippet.slice(cursor), marked: false });
  }
  return out;
}

export interface RelevanceTagProps {
  hit: QueryHit;
  /** How many snippet lines to show (default 2). */
  maxSnippets?: number;
  className?: string;
}

export function RelevanceTag({ hit, maxSnippets = 2, className }: RelevanceTagProps) {
  if (hit.relevance == null) return null;
  const snippets = hit.matched.slice(0, maxSnippets);

  return (
    <div
      className={cn("flex flex-col gap-1", className)}
      data-demo-id={`query-relevance-${hit.venture.venture_id}`}
    >
      <span className="mono-label tabular inline-flex w-fit items-center gap-1.5 rounded-full border border-electric px-2 py-0.5 text-electric">
        match {hit.relevance.toFixed(2)}
      </span>
      {snippets.map((s, i) => (
        <p key={`${s.field}-${i}`} className="max-w-measure text-mono-data leading-snug text-quiet">
          <span className="mono-label mr-1.5 normal-case text-quiet/70">{fieldLabel(s.field)}</span>
          {segmentsOf(s).map((seg, j) =>
            seg.marked ? (
              <mark key={j} className="bg-electric-wash text-ink">
                {seg.text}
              </mark>
            ) : (
              <span key={j}>{seg.text}</span>
            ),
          )}
        </p>
      ))}
    </div>
  );
}
