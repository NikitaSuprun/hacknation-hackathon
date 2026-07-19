/**
 * Controller hook for the venture query bar. Pure client-side: it holds the
 * VentureQuery state and derives hits from the pool with useMemo, so typing
 * re-ranks the ~11-row demo pool synchronously (and the fetched live ranking
 * through the exact same code path).
 */
import { useCallback, useMemo, useState } from "react";
import type { RankedVenture } from "@/lib/domain/types";
import {
  countActiveFilters,
  emptyQuery,
  runQuery,
  type QueryHit,
  type VentureQuery,
} from "@/lib/query";

export interface UseVentureQuery {
  query: VentureQuery;
  setQuery: (q: VentureQuery) => void;
  /** Filtered + (when the query has text) relevance-ranked pool. */
  hits: QueryHit[];
  /** Active constraint count — free text counts as one. */
  activeCount: number;
  reset: () => void;
}

export function useVentureQuery(ventures: RankedVenture[]): UseVentureQuery {
  const [query, setQuery] = useState<VentureQuery>(emptyQuery);

  const hits = useMemo(() => runQuery(ventures, query), [ventures, query]);
  const activeCount = useMemo(() => countActiveFilters(query), [query]);
  const reset = useCallback(() => setQuery(emptyQuery()), []);

  return { query, setQuery, hits, activeCount, reset };
}
