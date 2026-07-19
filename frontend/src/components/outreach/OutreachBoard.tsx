import { Fragment, useEffect, useMemo, useRef, useSyncExternalStore, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Skeleton } from "@/components/ui/skeleton";
import { dataSource } from "@/lib/data";
import type { OutreachRow, OutreachStatus, RankedVenture } from "@/lib/domain/types";
import { cn, formatScore } from "@/lib/utils";
import { OutreachCard } from "@/components/outreach/OutreachCard";
import { ShortlistCard } from "@/components/outreach/ShortlistCard";
import { getDB, getVersion, subscribe } from "@/mocks/state";
import "./outreach.css";

/**
 * The kanban over the outreach state machine. Lives on continuous paper —
 * no column wells, 1px vertical hairlines only. The board advances purely
 * via status changes (send action + founder flow); there is no drag & drop.
 *
 * DDL statuses grouped into display columns:
 *   Contacted    draft · approved · sent · replied · bounced
 *   Consented    consented · interview_scheduled · interview_started
 *   Interviewed  interviewed
 *   Closed       closed · declined · opted_out · expired  (muted)
 *
 * An Investment column sits between Interviewed and Closed so the happy
 * path reads left to right; it lists ventures in db.investmentProcess.
 */
interface ColumnDef {
  id: string;
  label: string;
  statuses: readonly OutreachStatus[];
  muted?: boolean;
}

const OUTREACH_COLUMNS: readonly ColumnDef[] = [
  { id: "contacted", label: "Contacted", statuses: ["draft", "approved", "sent", "replied", "bounced"] },
  { id: "consented", label: "Consented", statuses: ["consented", "interview_scheduled", "interview_started"] },
  { id: "interviewed", label: "Interviewed", statuses: ["interviewed"] },
  { id: "closed", label: "Closed", statuses: ["closed", "declined", "opted_out", "expired"], muted: true },
];

const COLUMN_CLASS =
  "flex flex-col gap-3 border-line py-2 max-md:border-b max-md:py-6 md:min-h-[440px] md:border-r md:px-4 md:first:pl-0 md:last:border-r-0 md:last:pr-0";

function BoardColumn({
  label,
  count,
  muted,
  children,
}: {
  label: string;
  count: number;
  muted?: boolean;
  children: ReactNode;
}) {
  return (
    <section className={COLUMN_CLASS}>
      <header className={cn("mb-2 flex items-baseline justify-between", muted && "opacity-70")}>
        <span className="mono-label">{label}</span>
        <span className="font-mono text-mono-label tabular text-quiet">
          {String(count).padStart(2, "0")}
        </span>
      </header>
      {children}
    </section>
  );
}

function ColumnEmpty() {
  return <span className="font-mono text-mono-label text-quiet opacity-50">—</span>;
}

/** Compact card for a venture the committee moved into the investment process. */
function InvestmentCard({ venture, thesisId }: { venture: RankedVenture; thesisId: string }) {
  return (
    <Link
      to={`/t/${thesisId}/venture/${venture.venture_id}`}
      data-demo-id={`investment-card-${venture.venture_id}`}
      className="block animate-fade-up border border-line bg-paper p-3 transition-colors duration-120 ease-swift hover:border-line-strong hover:bg-wash"
    >
      <div className="flex items-baseline justify-between gap-2">
        <p className="truncate text-small font-medium text-ink">{venture.name}</p>
        <span className="shrink-0 font-mono text-mono-data tabular text-ink">
          {formatScore(venture.final_score)}
        </span>
      </div>
      <p className="mt-1 truncate text-[13px] text-quiet">{venture.one_liner}</p>
      <span className="mt-2 inline-flex items-center rounded-full border border-line px-2 py-px font-mono text-[11px] uppercase leading-4 tracking-[0.06em] text-quiet">
        in process
      </span>
    </Link>
  );
}

function BoardSkeleton() {
  return (
    <div className="mt-10 grid grid-cols-1 md:grid-cols-6">
      {Array.from({ length: 6 }, (_, i) => (
        <div key={i} className={COLUMN_CLASS}>
          <div className="mb-2 flex items-baseline justify-between">
            <Skeleton className="h-4 w-20" />
            <Skeleton className="h-4 w-6" />
          </div>
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
          {i < 2 && <Skeleton className="h-24 w-full" />}
        </div>
      ))}
    </div>
  );
}

export function OutreachBoard({ thesisId }: { thesisId: string }) {
  const ds = dataSource();
  const { data: outreach, isLoading: outreachLoading } = useQuery({
    queryKey: ["outreach", thesisId],
    queryFn: () => ds.listOutreach(thesisId),
    // Founder-flow transitions land without a local mutation — poll lightly.
    refetchInterval: 4000,
  });
  const { data: ranking, isLoading: rankingLoading } = useQuery({
    queryKey: ["ranking", thesisId],
    queryFn: () => ds.getRanking(thesisId),
  });

  const rows = useMemo(() => outreach ?? [], [outreach]);

  // Previous statuses (last committed render) — a status change replays the
  // card's fade-up (via key) and flips its chip.
  const prevStatuses = useRef<Map<string, OutreachStatus>>(new Map());
  const changed = new Map<string, boolean>();
  for (const row of rows) {
    const prev = prevStatuses.current.get(row.outreach_id);
    changed.set(row.outreach_id, prev !== undefined && prev !== row.status);
  }
  useEffect(() => {
    const next = new Map<string, OutreachStatus>();
    for (const row of rows) next.set(row.outreach_id, row.status);
    prevStatuses.current = next;
  }, [rows]);

  const venturesById = useMemo(() => {
    const map = new Map<string, RankedVenture>();
    for (const venture of ranking ?? []) map.set(venture.venture_id, venture);
    return map;
  }, [ranking]);

  // Investment column: subscribe to the mock store so a "Start investment
  // process" click lands here live. Computed per render (the store array is
  // mutated in place, so memoizing on its reference would go stale).
  useSyncExternalStore(subscribe, getVersion);
  const investmentVentures = getDB()
    .investmentProcess.map((id) => venturesById.get(id))
    .filter((venture): venture is RankedVenture => venture !== undefined);

  // Shortlist: ranked ventures with no outreach row yet, top 6 by score.
  const shortlist = useMemo(() => {
    const contacted = new Set(rows.map((row) => row.venture_id));
    return [...(ranking ?? [])]
      .filter((venture) => !contacted.has(venture.venture_id))
      .sort((a, b) => b.final_score - a.final_score)
      .slice(0, 6);
  }, [ranking, rows]);

  const grouped = useMemo(() => {
    const byColumn = new Map<string, OutreachRow[]>();
    for (const column of OUTREACH_COLUMNS) byColumn.set(column.id, []);
    for (const row of rows) {
      const column = OUTREACH_COLUMNS.find((c) => c.statuses.includes(row.status));
      if (column) byColumn.get(column.id)!.push(row);
    }
    for (const list of byColumn.values()) {
      list.sort((a, b) =>
        (b.last_event_at ?? b.updated_at).localeCompare(a.last_event_at ?? a.updated_at),
      );
    }
    return byColumn;
  }, [rows]);

  if (outreachLoading || rankingLoading) return <BoardSkeleton />;

  return (
    <div data-demo-id="outreach-board" className="mt-10 grid grid-cols-1 md:grid-cols-6">
      <BoardColumn label="Shortlist" count={shortlist.length}>
        {shortlist.map((venture) => (
          <ShortlistCard key={venture.venture_id} venture={venture} thesisId={thesisId} />
        ))}
        {shortlist.length === 0 && <ColumnEmpty />}
      </BoardColumn>

      {rows.length === 0 && investmentVentures.length === 0 ? (
        <div className="flex min-h-[200px] items-center justify-center px-6 py-10 md:col-span-5 md:min-h-[440px]">
          <div className="animate-fade-in text-center">
            <p className="mono-label mb-3">Pipeline empty</p>
            <p className="text-body text-ink">No candidacies sent yet.</p>
            <Link
              to={`/t/${thesisId}/ranking`}
              className="mt-1 inline-block text-small text-quiet underline underline-offset-4 transition-colors duration-120 ease-swift hover:text-ink"
            >
              Choose a venture from the ranking.
            </Link>
          </div>
        </div>
      ) : (
        OUTREACH_COLUMNS.map((column) => {
          const list = grouped.get(column.id) ?? [];
          return (
            <Fragment key={column.id}>
              {/* Investment sits between Interviewed and Closed: the happy path reads left to right. */}
              {column.id === "closed" && (
                <BoardColumn label="Investment" count={investmentVentures.length}>
                  {investmentVentures.map((venture) => (
                    <InvestmentCard
                      key={venture.venture_id}
                      venture={venture}
                      thesisId={thesisId}
                    />
                  ))}
                  {investmentVentures.length === 0 && (
                    <span className="font-mono text-mono-label text-quiet opacity-50">·</span>
                  )}
                </BoardColumn>
              )}
              <BoardColumn label={column.label} count={list.length} muted={column.muted}>
                {list.map((row) => (
                  <OutreachCard
                    // Status in the key: a state change remounts the card, replaying fade-up.
                    key={`${row.outreach_id}:${row.status}`}
                    row={row}
                    ventureName={venturesById.get(row.venture_id)?.name ?? row.to_email}
                    flipChip={changed.get(row.outreach_id) === true}
                    muted={column.muted}
                  />
                ))}
                {list.length === 0 && <ColumnEmpty />}
              </BoardColumn>
            </Fragment>
          );
        })
      )}
    </div>
  );
}
