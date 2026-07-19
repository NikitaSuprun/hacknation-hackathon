import {
  CATEGORY_KEYS,
  type CategoryKey,
  type RankedVenture,
  type ScoreWeights,
  weightKey,
} from "@/lib/domain/types";

const SCORE_COLUMN: Record<CategoryKey, keyof RankedVenture> = {
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

export function categoryScoresOf(v: RankedVenture): Record<CategoryKey, number | null> {
  const out = {} as Record<CategoryKey, number | null>;
  for (const key of CATEGORY_KEYS) {
    out[key] = v[SCORE_COLUMN[key]] as number | null;
  }
  return out;
}

/**
 * final = round(Σ w·s / Σ w, 1) over categories with a score, N/A weight is
 * redistributed pro-rata. Mirrors the canonical implementations exactly
 * (app/rescoring.py::client_final_score and app/static/app.js::rerankScore),
 * so mock, live re-rank, and server rescore all agree to the decimal.
 */
export function computeFinalScore(
  scores: Partial<Record<CategoryKey, number | null>>,
  weights: ScoreWeights,
): number {
  let num = 0;
  let den = 0;
  for (const key of CATEGORY_KEYS) {
    const s = scores[key];
    const w = weights[weightKey(key)] as number;
    if (s != null && w > 0) {
      num += w * s;
      den += w;
    }
  }
  if (den <= 0) return 0;
  return Math.round((num / den) * 10) / 10;
}

/**
 * Recompute every final score under the given weights and sort descending.
 * Returns new objects, never mutates. Fast enough to run on slider input
 * (10 ventures × 9 categories); the WS-F acceptance is <100 ms with no network.
 */
export function rerank(ventures: RankedVenture[], weights: ScoreWeights): RankedVenture[] {
  return ventures
    .map((v) => ({ ...v, final_score: computeFinalScore(categoryScoresOf(v), weights) }))
    .sort((a, b) => b.final_score - a.final_score);
}
