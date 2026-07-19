import { NavLink, Outlet, Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { dataSource } from "@/lib/data";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { label: "Ranking", path: "ranking" },
  { label: "Outreach", path: "outreach" },
  { label: "Weights", path: "weights" },
  { label: "Ideal candidate", path: "ideal" },
] as const;

/**
 * The investor shell: hairline top bar with the CHOSEN wordmark, section nav,
 * and the data-mode chip. Content renders on the 1176px grid below.
 */
export function AppShell() {
  const ds = dataSource();
  const { data: theses } = useQuery({
    queryKey: ["theses"],
    queryFn: () => ds.listTheses(),
  });
  const thesis = theses?.[0];

  return (
    <div className="flex min-h-screen flex-col bg-paper">
      <header className="hairline-b sticky top-0 z-40 bg-paper/95 backdrop-blur-sm">
        <div className="mx-auto flex h-14 w-full max-w-grid items-center justify-between px-gutter">
          <div className="flex items-center gap-8">
            <Link
              to="/"
              className="font-display text-[15px] font-semibold uppercase tracking-[0.08em] text-ink"
            >
              Chosen
            </Link>
            <nav className="hidden items-center gap-1 md:flex">
              <NavLink
                to="/thesis"
                className={({ isActive }) =>
                  cn(
                    "rounded-ctrl px-3 py-1.5 text-small transition-colors duration-120 ease-swift",
                    isActive ? "bg-wash text-ink" : "text-quiet hover:bg-wash hover:text-ink",
                  )
                }
              >
                Thesis
              </NavLink>
              {thesis &&
                NAV_ITEMS.map((item) => (
                  <NavLink
                    key={item.path}
                    to={`/t/${thesis.thesis_id}/${item.path}`}
                    className={({ isActive }) =>
                      cn(
                        "rounded-ctrl px-3 py-1.5 text-small transition-colors duration-120 ease-swift",
                        isActive ? "bg-wash text-ink" : "text-quiet hover:bg-wash hover:text-ink",
                      )
                    }
                  >
                    {item.label}
                  </NavLink>
                ))}
              <NavLink
                to="/admin"
                className={({ isActive }) =>
                  cn(
                    "rounded-ctrl px-3 py-1.5 text-small transition-colors duration-120 ease-swift",
                    isActive ? "bg-wash text-ink" : "text-quiet hover:bg-wash hover:text-ink",
                  )
                }
              >
                Admin
              </NavLink>
            </nav>
          </div>
          <div className="flex items-center gap-4">
            {ds.mode === "mock" && (
              <span className="mono-label rounded-full border border-line-strong px-2.5 py-0.5">
                Demo data
              </span>
            )}
            <span className="hidden font-mono text-mono-data text-quiet sm:block">
              {thesis?.owner_email ?? ""}
            </span>
          </div>
        </div>
      </header>
      <main className="mx-auto w-full max-w-grid flex-1 px-gutter">
        <Outlet />
      </main>
    </div>
  );
}
