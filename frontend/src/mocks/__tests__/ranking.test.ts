/**
 * Arithmetic ground truth for the demo: every hand-authored final score must
 * be exactly what computeFinalScore yields, the ranked order must match the
 * demo plan under both weight settings, and the interview re-score beat must
 * land on the promised numbers.
 */
import { afterEach, describe, expect, it } from "vitest";
import { categoryScoresOf, computeFinalScore, rerank } from "@/lib/ranking/rerank";
import { EXTRA_VENTURES } from "@/mocks/fixtures/extraVentures";
import { GRASPLAB_ID, seedDB } from "@/mocks/fixtures/seed";
import { completeInterviewMutation } from "@/mocks/scenarios";
import { getDB, mutate, resetDB } from "@/mocks/state";

/** The demo-plan table: name -> final under default weights. */
const TABLE: Record<string, number> = {
  Axonode: 76.3,
  TactiSense: 72.8,
  "FastSim Labs": 70.1,
  "Wayline Robotics": 68.6,
  Ceresbot: 67.0,
  Périsurg: 63.2,
  CairnSight: 60.7,
  Loopwise: 57.2,
  "Otterix Automation": 43.7,
};

describe("extra-venture arithmetic (default weights)", () => {
  it("every stored final equals computeFinalScore over its categories", () => {
    const { weights } = seedDB();
    for (const venture of EXTRA_VENTURES) {
      const computed = computeFinalScore(categoryScoresOf(venture), weights);
      expect(computed, venture.name).toBe(TABLE[venture.name]);
      expect(venture.final_score, venture.name).toBe(TABLE[venture.name]);
    }
  });

  it("N/A categories redistribute weight instead of scoring zero", () => {
    const { weights } = seedDB();
    const fastsim = EXTRA_VENTURES.find((v) => v.name === "FastSim Labs")!;
    expect(fastsim.s_schools).toBeNull();
    expect(fastsim.s_prior_collaboration).toBeNull();
    // Present categories only: 0.15*76+0.05*45+0.15*82+0.15*74+0.1*70+0.1*58+0.1*62 over 0.80
    expect(computeFinalScore(categoryScoresOf(fastsim), weights)).toBe(70.1);
  });

  it("rerank puts Axonode #1 at 76.3 and GraspLab #2 at 75.1", () => {
    const seed = seedDB();
    const ranked = rerank(seed.ventures, seed.weights);
    expect(ranked[0]?.name).toBe("Axonode");
    expect(ranked[0]?.final_score).toBe(76.3);
    expect(ranked[1]?.venture_id).toBe(GRASPLAB_ID);
    expect(ranked[1]?.final_score).toBe(75.1);
  });
});

describe("re-rank under w_prior_collaboration = 0.20", () => {
  it("GraspLab 76.5 takes #1, TactiSense 73.9 #2, Axonode 72.0 #3", () => {
    const seed = seedDB();
    const ranked = rerank(seed.ventures, { ...seed.weights, w_prior_collaboration: 0.2 });
    expect(ranked.slice(0, 3).map((v) => [v.name, v.final_score])).toEqual([
      ["GraspLab", 76.5],
      ["TactiSense", 73.9],
      ["Axonode", 72],
    ]);
  });
});

describe("interview re-score beat", () => {
  afterEach(() => resetDB());

  it("completeInterviewMutation with the 0.20 weights lands GraspLab at 79.9 / 0.82", () => {
    resetDB();
    mutate((db) => {
      db.weights = { ...db.weights, w_prior_collaboration: 0.2 };
    });
    completeInterviewMutation();

    const db = getDB();
    const grasplab = db.ventures.find((v) => v.venture_id === GRASPLAB_ID)!;
    expect(grasplab.final_score).toBe(79.9);
    expect(grasplab.confidence).toBe(0.82);
    expect(grasplab.funding_signal).toBe("confirmed_none");

    const history = db.scoreHistory[GRASPLAB_ID]!;
    expect(history[0]?.score_id).toBe("score-post-interview");
    // The pre-interview row stays second, untouched.
    expect(history[1]?.score_id).toBe(`score-${GRASPLAB_ID}-1`);
    expect(history[1]?.final_score).toBe(75.1);
  });

  it("the interview swaps the post memo in for GraspLab", () => {
    resetDB();
    completeInterviewMutation();
    const db = getDB();
    expect(db.memos[GRASPLAB_ID]?.memo_id).toBe("memo-grasplab-post");
    const market = db.memos[GRASPLAB_ID]?.sections.market_tam_sam_som;
    expect(market?.som).toContain("CHF 115M");
  });
});
