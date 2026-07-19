/**
 * Admin · Database — the read-only instrument over everything CHOSEN holds:
 * medallion-layer stats, the people/venture provenance graph, and a raw
 * table browser. All data is local (contract fixtures + the live demo
 * store); no network.
 */
import { useState } from "react";
import { cn } from "@/lib/utils";
import { OverviewView } from "@/components/admin/OverviewView";
import { GraphView } from "@/components/admin/GraphView";
import { TableBrowserView } from "@/components/admin/TableBrowserView";
import { fixtureTables } from "@/components/admin/data";

const VIEWS = [
  { key: "overview", label: "Overview" },
  { key: "graph", label: "People graph" },
  { key: "tables", label: "Tables" },
] as const;

type ViewKey = (typeof VIEWS)[number]["key"];

const TABLE_COUNT = fixtureTables().length;
const ROW_COUNT = fixtureTables().reduce((n, t) => n + t.rows.length, 0);

export default function AdminPage() {
  const [view, setView] = useState<ViewKey>("overview");

  return (
    <div className="py-gutter-lg">
      <p className="mono-label mb-2">Admin — internal database</p>
      <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-2">
        <h1 className="font-display text-h1">Database</h1>
        <p className="font-mono text-mono-data tabular text-quiet">
          {TABLE_COUNT} tables · {ROW_COUNT} fixture rows · bronze → silver → gold
        </p>
      </div>

      <nav className="mt-6 flex gap-6 border-b border-line" aria-label="Database views">
        {VIEWS.map((v) => {
          const active = v.key === view;
          return (
            <button
              key={v.key}
              type="button"
              onClick={() => setView(v.key)}
              className={cn(
                "-mb-px border-b-2 pb-2 font-mono text-mono-label uppercase tracking-[0.06em] transition-colors duration-120 ease-swift",
                active
                  ? "border-electric text-ink"
                  : "border-transparent text-quiet hover:text-ink",
              )}
              aria-current={active ? "page" : undefined}
            >
              {v.label}
            </button>
          );
        })}
      </nav>

      {view === "overview" && <OverviewView />}
      {view === "graph" && <GraphView />}
      {view === "tables" && <TableBrowserView />}
    </div>
  );
}
