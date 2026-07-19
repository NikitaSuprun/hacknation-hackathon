/**
 * Admin · Overview — the pipeline at a glance. Row counts per table grouped
 * by medallion layer, a thin silver→gold flow strip, and ER health over
 * person_source_links. Read-only; gold counts come from the live store.
 */
import { useMemo } from "react";
import { cn } from "@/lib/utils";
import {
  buildErHealth,
  buildLayerStats,
  getDB,
  useLiveVersion,
  type LayerStats,
  type StatCard,
} from "./data";

function FlowArrow() {
  return (
    <div className="relative mx-2 hidden h-px min-w-8 flex-1 bg-line sm:block" aria-hidden>
      <span className="absolute -right-px top-1/2 h-0 w-0 -translate-y-1/2 border-y-[3px] border-l-[5px] border-y-transparent border-l-line-strong" />
    </div>
  );
}

function FlowStage({ count, label }: { count: string; label: string }) {
  return (
    <div className="flex items-baseline gap-2">
      <span className="font-mono text-body tabular text-ink">{count}</span>
      <span className="mono-label">{label}</span>
    </div>
  );
}

function StatCardCell({ card }: { card: StatCard }) {
  return (
    <div className="rounded-none border border-line bg-paper p-4">
      <p className="font-mono text-[28px] leading-none tabular text-ink">{card.count}</p>
      <p className="mono-label mt-3">{card.label}</p>
      <p className="mt-0.5 font-mono text-[11px] leading-4 text-quiet">
        {card.source === "live" ? "live store" : "fixture"}
      </p>
    </div>
  );
}

function LayerSection({ stats }: { stats: LayerStats }) {
  return (
    <section className="mt-8">
      <div className="flex items-baseline gap-3">
        <h2 className="mono-label text-ink">{stats.eyebrow}</h2>
        <p className="text-small text-quiet">{stats.caption}</p>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        {stats.cards.map((card) => (
          <StatCardCell key={card.label} card={card} />
        ))}
      </div>
    </section>
  );
}

export function OverviewView() {
  // The store mutates in place — key derived data on the store version.
  const version = useLiveVersion();
  const db = getDB();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const layers = useMemo(() => buildLayerStats(db), [version]);
  const er = useMemo(() => buildErHealth(), []);

  const ventureCount = db.ventures.length;
  const memoCount = Object.keys(db.memos).length;
  const silverCards = layers.find((l) => l.layer === "silver")?.cards ?? [];
  const countOf = (label: string) => silverCards.find((c) => c.label === label)?.count ?? 0;

  return (
    <div className="animate-fade-up pb-gutter-lg">
      {/* Medallion flow strip */}
      <div className="mt-8 flex flex-wrap items-center gap-y-2 rounded-none border border-line bg-paper px-4 py-3">
        <FlowStage count="—" label="bronze · raw scrapes" />
        <FlowArrow />
        <FlowStage count={String(countOf("source records"))} label="source records" />
        <FlowArrow />
        <FlowStage count={String(countOf("persons"))} label="persons" />
        <FlowArrow />
        <FlowStage count={String(ventureCount)} label="ventures" />
        <FlowArrow />
        <FlowStage count={String(memoCount)} label="memos" />
      </div>
      <p className="mt-2 font-mono text-[11px] text-quiet">
        Bronze lands in the warehouse only — see bronze_ref pointers on source records.
      </p>

      {layers.map((stats) => (
        <LayerSection key={stats.layer} stats={stats} />
      ))}

      {/* ER health */}
      <section className="mt-10">
        <div className="flex items-baseline gap-3">
          <h2 className="mono-label text-ink">ER health</h2>
          <p className="text-small text-quiet">
            person_source_links by match_method · avg confidence{" "}
            <span className="font-mono tabular">{er.avgConfidence.toFixed(2)}</span> ·{" "}
            <span className="font-mono tabular">{er.totalActive}</span> active /{" "}
            <span className="font-mono tabular">{er.totalRetracted}</span> retracted
          </p>
        </div>
        <div className="mt-3 overflow-x-auto rounded-none border border-line">
          <table className="w-full min-w-[560px] border-collapse text-left">
            <thead>
              <tr className="hairline-b">
                <th className="mono-label px-4 py-2 font-normal">method</th>
                <th className="mono-label px-4 py-2 font-normal">class</th>
                <th className="mono-label px-4 py-2 text-right font-normal">links</th>
                <th className="mono-label px-4 py-2 text-right font-normal">avg conf</th>
                <th className="mono-label px-4 py-2 text-right font-normal">active</th>
                <th className="mono-label px-4 py-2 text-right font-normal">retracted</th>
              </tr>
            </thead>
            <tbody>
              {er.methods.map((m) => (
                <tr key={m.method} className="hairline-b last:border-b-0">
                  <td className="px-4 py-1.5 font-mono text-mono-data text-ink">{m.method}</td>
                  <td className="px-4 py-1.5 font-mono text-mono-data text-quiet">{m.kind}</td>
                  <td className="px-4 py-1.5 text-right font-mono text-mono-data tabular text-ink">
                    {m.links}
                  </td>
                  <td className="px-4 py-1.5 text-right font-mono text-mono-data tabular text-ink">
                    {m.avgConfidence.toFixed(2)}
                  </td>
                  <td className="px-4 py-1.5 text-right font-mono text-mono-data tabular text-ink">
                    {m.active}
                  </td>
                  <td
                    className={cn(
                      "px-4 py-1.5 text-right font-mono text-mono-data tabular",
                      m.retracted > 0 ? "text-danger" : "text-quiet",
                    )}
                  >
                    {m.retracted}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
