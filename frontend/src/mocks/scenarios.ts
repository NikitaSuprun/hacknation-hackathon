/**
 * Named points in the demo story, implemented as a synchronous replay of the
 * same mutations the UI performs, so a scenario jump always lands in a state
 * the app could genuinely reach by clicking.
 */
import { getDB, mutate, resetDB } from "@/mocks/state";
import { GRASPLAB_ID, buildSentOutreachRow, snapshotOf } from "@/mocks/fixtures/seed";
import { INTERVIEW_SCRIPT } from "@/mocks/fixtures/chatScript";
import { categoryScoresOf, computeFinalScore } from "@/lib/ranking/rerank";
import type { ChatMessage } from "@/lib/domain/types";

export type ScenarioId =
  | "initial"
  | "thesis-ready"
  | "outreach-sent"
  | "consented"
  | "candidacy-complete"
  | "interview-done";

export const SCENARIO_ORDER: ScenarioId[] = [
  "initial",
  "thesis-ready",
  "outreach-sent",
  "consented",
  "candidacy-complete",
  "interview-done",
];

/**
 * Interview completion: flip statuses, apply the post-interview score patch,
 * swap in the post memo. Shared by MockDataSource.completeInterview() and the
 * scenario replay, one code path for the beat-13 re-score.
 */
export function completeInterviewMutation(): void {
  mutate((db) => {
    db.interview.stage = "completed";
    const row = db.outreach.find((o) => o.venture_id === GRASPLAB_ID);
    if (row) {
      row.status = "interviewed";
      row.last_event_at = new Date().toISOString();
    }
    const patch = db.postInterviewPatch;
    if (patch) {
      const venture = db.ventures.find((v) => v.venture_id === patch.ventureId);
      if (venture) {
        for (const [key, score] of Object.entries(patch.scores)) {
          if (score == null) continue;
          if (key === "ideal_match") venture.ideal_match = score;
          else (venture as unknown as Record<string, unknown>)[`s_${key}`] = score;
          const cat = venture.breakdown.categories[key as keyof typeof venture.breakdown.categories];
          if (cat) {
            cat.score = score;
            cat.confidence = patch.confidence;
          }
        }
        venture.confidence = patch.confidence;
        venture.scored_at = new Date().toISOString();
        venture.final_score = computeFinalScore(categoryScoresOf(venture), db.weights);
        if (patch.fundingSignalAfter) venture.funding_signal = patch.fundingSignalAfter;
        // Append the post-interview row to score history (newest first).
        (db.scoreHistory[patch.ventureId] ??= []).unshift(
          snapshotOf(venture, "score-post-interview"),
        );
      }
      const postMemo = db.postMemos[patch.ventureId];
      if (postMemo) db.memos[patch.ventureId] = postMemo;
    }
  });
}

function fullTranscript(): ChatMessage[] {
  const messages: ChatMessage[] = [];
  INTERVIEW_SCRIPT.forEach((turn, i) => {
    messages.push({
      id: `ai-${i}`,
      role: "interviewer",
      text: turn.ai,
      at: new Date(2026, 6, 16, 10, i * 2).toISOString(),
    });
    if (turn.founder) {
      messages.push({
        id: `founder-${i}`,
        role: "founder",
        text: turn.founder,
        at: new Date(2026, 6, 16, 10, i * 2 + 1).toISOString(),
      });
    }
  });
  return messages;
}

const STEPS: Record<Exclude<ScenarioId, "initial">, () => void> = {
  "thesis-ready": () =>
    mutate((db) => {
      db.thesisIntake.stage = "confirmed";
      db.thesisIntake.source = "https://fund.example/investment-thesis";
    }),
  "outreach-sent": () =>
    mutate((db) => {
      db.outreach = db.outreach.filter((o) => o.venture_id !== GRASPLAB_ID);
      db.outreach.push(buildSentOutreachRow());
      const venture = db.ventures.find((v) => v.venture_id === GRASPLAB_ID);
      if (venture) venture.status = "outreach";
    }),
  consented: () =>
    mutate((db) => {
      db.interview.stage = "consented";
      db.interview.consented = true;
      db.interview.consent_text =
        "I agree to share information in this interview with the fund for the purpose of this review.";
      const row = db.outreach.find((o) => o.venture_id === GRASPLAB_ID);
      if (row) {
        row.status = "consented";
        row.consent_at = new Date().toISOString();
      }
    }),
  "candidacy-complete": () =>
    mutate((db) => {
      db.interview.structured = {
        linkedin_url: "https://www.linkedin.com/in/lena-fischer-robotics",
        github_url: "https://github.com/lenafischer",
        cv_file: { kind: "cv", name: "Lena_Fischer_CV.pdf", size_bytes: 145_408, url: null },
        pitch_file: { kind: "pitch", name: "GraspLab_Pitch.pdf", size_bytes: 2_202_009, url: null },
        traction_notes:
          "3 paid warehouse pilots since April. Design-partner waitlist: 41 companies.",
      };
    }),
  "interview-done": () => {
    mutate((db) => {
      db.interview.transcript = fullTranscript();
    });
    completeInterviewMutation();
  },
};

/** Rebuild state to the named scenario by replaying every step up to it. */
export function applyScenario(id: ScenarioId): void {
  resetDB();
  const upto = SCENARIO_ORDER.indexOf(id);
  for (let i = 1; i <= upto; i++) {
    STEPS[SCENARIO_ORDER[i] as Exclude<ScenarioId, "initial">]();
  }
}

export function currentScenarioGuess(): ScenarioId {
  const db = getDB();
  if (db.interview.stage === "completed") return "interview-done";
  if (db.interview.structured) return "candidacy-complete";
  if (db.interview.consented) return "consented";
  if (db.outreach.some((o) => o.venture_id === GRASPLAB_ID && o.status !== "draft"))
    return "outreach-sent";
  if (db.thesisIntake.stage === "confirmed") return "thesis-ready";
  return "initial";
}
