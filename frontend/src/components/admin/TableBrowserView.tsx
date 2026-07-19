/**
 * Admin · Table browser, the "we can query the database" surface. Left rail
 * of contract-fixture tables with counts; right side a paginated mono table
 * (20/page) with a text filter. Object/array cells render as truncated JSON
 * and expand into a pretty-printed Dialog.
 */
import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { fixtureTables, type Raw, type TableDef } from "./data";

const PAGE_SIZE = 20;
const MAX_COLUMNS = 8;
const CELL_CHARS = 28;

const LAYER_ORDER: { key: TableDef["layer"]; label: string }[] = [
  { key: "silver", label: "Silver" },
  { key: "gold", label: "Gold" },
  { key: "ops", label: "Ops" },
];

function columnScore(key: string): number {
  if (/^(name|full_name|title|subject)$/.test(key)) return 96;
  if (/(^|_)id$/.test(key)) return 94;
  if (/^(display_name|one_liner|headline|label)$/.test(key)) return 90;
  if (key === "status") return 86;
  if (/^(source|match_method|method|role|role_norm|channel|venue|stage|connection_type|legal_form|source_key)$/.test(key)) return 80;
  if (
    /^(final_score|confidence|match_confidence|weight|score|stars|forks|commit_count|citation_count|data_quality_score|importance|is_latest|included)$/.test(
      key,
    )
  )
    return 74;
  if (/(_at|_date)$/.test(key) || /^(first_seen|last_seen)$/.test(key)) return 40;
  return 55;
}

function pickColumns(rows: Raw[]): string[] {
  const keys: string[] = [];
  for (const row of rows) {
    for (const k of Object.keys(row)) if (!keys.includes(k)) keys.push(k);
  }
  const ranked = [...keys].sort(
    (a, b) => columnScore(b) - columnScore(a) || keys.indexOf(a) - keys.indexOf(b),
  );
  // Don't let a wall of ids crowd out the payload columns.
  const chosen: string[] = [];
  let idCount = 0;
  for (const key of ranked) {
    const isId = /(^|_)id$/.test(key);
    if (isId && idCount >= 2) continue;
    if (isId) idCount += 1;
    chosen.push(key);
    if (chosen.length >= MAX_COLUMNS) break;
  }
  return chosen;
}

function truncate(s: string, max: number): string {
  return s.length > max ? `${s.slice(0, max)}…` : s;
}

interface ExpandedCell {
  title: string;
  json: string;
}

function Cell({
  value,
  column,
  onExpand,
}: {
  value: unknown;
  column: string;
  onExpand: (cell: ExpandedCell) => void;
}) {
  if (value == null) {
    return <span className="text-quiet">-</span>;
  }
  if (typeof value === "object") {
    const compact = JSON.stringify(value) ?? "";
    return (
      <button
        type="button"
        onClick={() =>
          onExpand({ title: column, json: JSON.stringify(value, null, 2) ?? "" })
        }
        className="max-w-full truncate text-left text-quiet underline decoration-line underline-offset-2 transition-colors duration-120 ease-swift hover:text-ink"
        title="Expand JSON"
      >
        {truncate(compact, CELL_CHARS)}
      </button>
    );
  }
  const s = String(value);
  return (
    <span className="text-ink" title={s.length > CELL_CHARS ? s : undefined}>
      {truncate(s, CELL_CHARS)}
    </span>
  );
}

export function TableBrowserView() {
  const tables = useMemo(() => fixtureTables(), []);
  const [tableKey, setTableKey] = useState<string>(tables[0]?.key ?? "persons");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(0);
  const [expanded, setExpanded] = useState<ExpandedCell | null>(null);

  const table = tables.find((t) => t.key === tableKey) ?? tables[0];
  const columns = useMemo(() => pickColumns(table.rows), [table]);
  const haystacks = useMemo(
    () => table.rows.map((row) => JSON.stringify(row).toLowerCase()),
    [table],
  );

  const q = query.trim().toLowerCase();
  const filtered = useMemo(() => {
    if (!q) return table.rows;
    return table.rows.filter((_, i) => haystacks[i].includes(q));
  }, [table, haystacks, q]);

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const safePage = Math.min(page, pageCount - 1);
  const pageRows = filtered.slice(safePage * PAGE_SIZE, (safePage + 1) * PAGE_SIZE);
  const from = filtered.length === 0 ? 0 : safePage * PAGE_SIZE + 1;
  const to = safePage * PAGE_SIZE + pageRows.length;

  const selectTable = (key: string) => {
    setTableKey(key);
    setQuery("");
    setPage(0);
  };

  return (
    <div className="mt-8 flex animate-fade-up gap-0 overflow-hidden rounded-none border border-line">
      {/* left rail */}
      <nav className="w-60 shrink-0 overflow-y-auto border-r border-line bg-paper py-3" aria-label="Tables">
        {LAYER_ORDER.map(({ key, label }) => (
          <div key={key} className="mb-4 last:mb-0">
            <p className="mono-label px-4 pb-1">{label}</p>
            {tables
              .filter((t) => t.layer === key)
              .map((t) => {
                const active = t.key === table.key;
                return (
                  <button
                    key={t.key}
                    type="button"
                    onClick={() => selectTable(t.key)}
                    className={cn(
                      "flex w-full items-baseline justify-between gap-2 border-l-2 py-1 pl-[14px] pr-4 text-left font-mono text-mono-data transition-colors duration-120 ease-swift",
                      active
                        ? "border-electric bg-wash text-ink"
                        : "border-transparent text-quiet hover:bg-wash hover:text-ink",
                    )}
                    aria-current={active ? "true" : undefined}
                  >
                    <span className="truncate">{t.label}</span>
                    <span className="shrink-0 tabular">{t.rows.length}</span>
                  </button>
                );
              })}
          </div>
        ))}
      </nav>

      {/* table */}
      <div className="flex min-w-0 flex-1 flex-col bg-paper">
        <div className="hairline-b flex items-center justify-between gap-4 px-4 py-3">
          <div className="min-w-0">
            <span className="font-mono text-mono-data text-ink">{table.label}</span>
            <span className="ml-3 font-mono text-[11px] tabular text-quiet">
              {filtered.length} row{filtered.length === 1 ? "" : "s"}
              {q ? ` of ${table.rows.length}` : ""}
            </span>
          </div>
          <Input
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setPage(0);
            }}
            placeholder="Filter rows"
            className="h-8 w-56 font-mono text-mono-data"
            aria-label="Filter rows"
          />
        </div>

        <div className="min-h-[420px] flex-1 overflow-x-auto">
          <table className="w-full min-w-[720px] border-collapse text-left">
            <thead>
              <tr className="hairline-b">
                {columns.map((c) => (
                  <th key={c} className="mono-label whitespace-nowrap px-3 py-2 font-normal">
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {pageRows.map((row, i) => (
                <tr key={safePage * PAGE_SIZE + i} className="hairline-b align-baseline last:border-b-0 hover:bg-wash">
                  {columns.map((c) => (
                    <td key={c} className="max-w-[22ch] whitespace-nowrap px-3 py-1.5 font-mono text-mono-data">
                      <Cell value={row[c]} column={c} onExpand={setExpanded} />
                    </td>
                  ))}
                </tr>
              ))}
              {pageRows.length === 0 && (
                <tr>
                  <td colSpan={columns.length} className="px-3 py-8 text-center text-small text-quiet">
                    No rows match “{query}”.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="hairline-t flex items-center justify-between px-4 py-2">
          <span className="font-mono text-[11px] tabular text-quiet">
            rows {from}-{to} of {filtered.length} · page {safePage + 1}/{pageCount}
          </span>
          <div className="flex gap-1">
            <Button
              variant="ghost"
              size="sm"
              disabled={safePage === 0}
              onClick={() => setPage(safePage - 1)}
            >
              Prev
            </Button>
            <Button
              variant="ghost"
              size="sm"
              disabled={safePage >= pageCount - 1}
              onClick={() => setPage(safePage + 1)}
            >
              Next
            </Button>
          </div>
        </div>
      </div>

      {/* JSON cell expansion */}
      <Dialog open={expanded != null} onOpenChange={(open) => !open && setExpanded(null)}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle className="font-mono text-mono-data uppercase tracking-[0.06em]">
              {table.label} · {expanded?.title}
            </DialogTitle>
          </DialogHeader>
          <pre className="max-h-[60vh] overflow-auto border border-line bg-wash p-4 font-mono text-mono-data leading-relaxed text-ink">
            {expanded?.json}
          </pre>
        </DialogContent>
      </Dialog>
    </div>
  );
}
