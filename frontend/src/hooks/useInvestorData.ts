/**
 * Track B data hooks, thin, typed wrappers over the mock/live seam.
 * Query keys follow the shared contract: ["theses"], ["ranking", thesisId],
 * ["memo", ventureId], ["scores", ventureId], ["team", ventureId],
 * ["gaps", ventureId], ["weights", thesisId], ["ideal", thesisId].
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { dataSource } from "@/lib/data";
import {
  CATEGORY_KEYS,
  type CategoryKey,
  type RankedVenture,
  type ScoreSnapshot,
} from "@/lib/domain/types";

export function useTheses() {
  const ds = dataSource();
  return useQuery({ queryKey: ["theses"], queryFn: () => ds.listTheses() });
}

export function useRanking(thesisId: string) {
  const ds = dataSource();
  return useQuery({
    queryKey: ["ranking", thesisId],
    queryFn: () => ds.getRanking(thesisId),
    enabled: thesisId.length > 0,
  });
}

export function useWeights(thesisId: string) {
  const ds = dataSource();
  return useQuery({
    queryKey: ["weights", thesisId],
    queryFn: () => ds.getWeights(thesisId),
    enabled: thesisId.length > 0,
  });
}

export function useVentureScores(ventureId: string) {
  const ds = dataSource();
  return useQuery({
    queryKey: ["scores", ventureId],
    queryFn: () => ds.getVentureScores(ventureId),
    enabled: ventureId.length > 0,
  });
}

/** retry: false, "no memo" is a real state (VoiceLab), not a transient failure. */
export function useVentureMemo(ventureId: string) {
  const ds = dataSource();
  return useQuery({
    queryKey: ["memo", ventureId],
    queryFn: () => ds.getVentureMemo(ventureId),
    enabled: ventureId.length > 0,
    retry: false,
  });
}

export function useVentureTeam(ventureId: string) {
  const ds = dataSource();
  return useQuery({
    queryKey: ["team", ventureId],
    queryFn: () => ds.getVentureTeam(ventureId),
    enabled: ventureId.length > 0,
  });
}

export function useVentureGaps(ventureId: string) {
  const ds = dataSource();
  return useQuery({
    queryKey: ["gaps", ventureId],
    queryFn: () => ds.getVentureGaps(ventureId),
    enabled: ventureId.length > 0,
  });
}

export function useIdealCandidate(thesisId: string) {
  const ds = dataSource();
  return useQuery({
    queryKey: ["ideal", thesisId],
    queryFn: () => ds.getIdealCandidate(thesisId),
    enabled: thesisId.length > 0,
  });
}

/** Convenience: a single venture out of the ranked list (same cache entry). */
export function useVenture(thesisId: string, ventureId: string) {
  const query = useRanking(thesisId);
  const venture = useMemo(
    () => query.data?.find((v) => v.venture_id === ventureId),
    [query.data, ventureId],
  );
  return { ...query, venture };
}

const SNAPSHOT_COLUMN: Record<CategoryKey, keyof ScoreSnapshot> = {
  individual_experience: "s_individual_experience",
  schools: "s_schools",
  network_ties: "s_network_ties",
  prior_collaboration: "s_prior_collaboration",
  problem_realness: "s_problem_realness",
  product_defensibility: "s_product_defensibility",
  market: "s_market",
  traction: "s_traction",
  ideal_match: "ideal_match",
};

/** Category scores of a history snapshot, mirrors rerank.categoryScoresOf(). */
export function categoryScoresOfSnapshot(
  snapshot: ScoreSnapshot,
): Record<CategoryKey, number | null> {
  const out = {} as Record<CategoryKey, number | null>;
  for (const key of CATEGORY_KEYS) {
    out[key] = snapshot[SNAPSHOT_COLUMN[key]] as number | null;
  }
  return out;
}

export function isNeedsMoreData(v: RankedVenture): boolean {
  return v.quality_tier === "needs_more_data";
}

/**
 * Live cold start runs 5-10s, after ~3s of continuous loading, surface the
 * "Warming the warehouse" microcopy.
 */
export const COLD_START_HINT =
  "Warming the warehouse, first load takes a few seconds";

export function useColdStartHint(loading: boolean): boolean {
  const [show, setShow] = useState(false);
  useEffect(() => {
    if (!loading) {
      setShow(false);
      return;
    }
    const t = window.setTimeout(() => setShow(true), 3000);
    return () => window.clearTimeout(t);
  }, [loading]);
  return show && loading;
}

/**
 * FLIP-lite: watch an ordered id list; when the order changes, return the set
 * of ids that moved for exactly 240ms (the rank-change flash).
 */
export function useFlashOnReorder(ids: string[] | undefined): Set<string> {
  const prevRef = useRef<string[] | null>(null);
  const [flashed, setFlashed] = useState<Set<string>>(() => new Set());
  const key = ids?.join("|") ?? "";
  useEffect(() => {
    if (!ids || ids.length === 0) return;
    const prev = prevRef.current;
    prevRef.current = ids;
    if (!prev || prev.join("|") === key) return;
    const moved = ids.filter((id, i) => prev[i] !== id && prev.includes(id));
    if (moved.length === 0) return;
    setFlashed(new Set(moved));
    const t = window.setTimeout(() => setFlashed(new Set()), 240);
    return () => window.clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return flashed;
}
