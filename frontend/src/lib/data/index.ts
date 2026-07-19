/**
 * Mode selection — the one place the demo and the real app diverge.
 * Precedence: ?demo=1 / ?mode= URL param → localStorage → VITE_DATA_MODE →
 * default mock. The runtime toggle is the on-stage insurance: if the
 * warehouse dies mid-presentation, append ?mode=mock and keep talking.
 */
import type { DataSource } from "@/lib/data/DataSource";
import { MockDataSource } from "@/lib/data/MockDataSource";
import { LiveDataSource } from "@/lib/data/LiveDataSource";

export type DataMode = "mock" | "live";

const STORAGE_KEY = "chosen.mode";

function toggleAllowed(): boolean {
  return import.meta.env.VITE_ALLOW_MODE_TOGGLE !== "false";
}

export function resolveMode(): DataMode {
  if (typeof window !== "undefined" && toggleAllowed()) {
    const params = new URLSearchParams(window.location.search);
    if (params.get("demo") === "1") return "mock";
    const urlMode = params.get("mode");
    if (urlMode === "mock" || urlMode === "live") {
      localStorage.setItem(STORAGE_KEY, urlMode);
      return urlMode;
    }
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === "mock" || stored === "live") return stored;
  }
  const env = import.meta.env.VITE_DATA_MODE as string | undefined;
  return env === "live" ? "live" : "mock";
}

let instance: DataSource | null = null;

export function dataSource(): DataSource {
  if (!instance) {
    instance = resolveMode() === "live" ? new LiveDataSource() : new MockDataSource();
  }
  return instance;
}

/** Test-only escape hatch. */
export function _resetDataSourceForTests(): void {
  instance = null;
}
