/**
 * The demo script as data: fifteen beats in three acts.
 *
 * Act 1, the investor (beats 1-7): login, thesis intake with extraction,
 * ranking, semantic query, the GraspLab memo, weights behind the gear,
 * scheduling the AI interview.
 * Act 2, the founder (beats 8-12): invitation, consent, candidacy,
 * the shortened interview, finish.
 * Act 3, back to the investor (beats 13-15): the board has moved, the
 * re-scored memo plus a follow-up question, and the investment kickoff.
 *
 * The interview beat (B11) is generated from INTERVIEW_SCRIPT so script
 * changes expand the autopilot automatically.
 */
import { getDB } from "@/mocks/state";
import { GRASPLAB_ID } from "@/mocks/fixtures/seed";
import { INTERVIEW_SCRIPT } from "@/mocks/fixtures/chatScript";
import type { ScenarioId } from "@/mocks/scenarios";
import type { DemoCtx, DemoStep } from "@/demo/types";

export const BEAT_COUNT = 15;

/**
 * Fallback thesis id (the generated fixture). The engine resolves the real id
 * via dataSource().listTheses() at start; this only papers over a failure.
 */
export const FALLBACK_THESIS_ID = "aaaaaaaa-0000-4000-8000-000000000001";

/** State the mock store is put into when JUMPING to a beat (never during continuous play). */
export const BEAT_CHECKPOINT: Record<number, ScenarioId> = {
  1: "initial",
  2: "initial", // the intake happens IN beat 2
  3: "thesis-ready",
  4: "thesis-ready",
  5: "thesis-ready",
  6: "thesis-ready",
  7: "thesis-ready", // the send happens IN beat 7
  8: "outreach-sent",
  9: "outreach-sent",
  10: "consented",
  11: "candidacy-complete",
  12: "candidacy-complete",
  13: "interview-done",
  14: "interview-done",
  15: "interview-done",
};

const ranking = (ctx: DemoCtx) => `/t/${ctx.thesisId}/ranking`;
const outreach = (ctx: DemoCtx) => `/t/${ctx.thesisId}/outreach`;
const venture = (ctx: DemoCtx) => `/t/${ctx.thesisId}/venture/${GRASPLAB_ID}`;
const interview = () => "/interview/demo";

/** Interviewer messages that have fully landed in the mock transcript. */
function interviewerCount(): number {
  return getDB().interview.transcript.filter((m) => m.role === "interviewer").length;
}

/** Founder messages in the transcript (the follow-up reply arrives as one more). */
function founderCount(): number {
  return getDB().interview.transcript.filter((m) => m.role === "founder").length;
}

const SCRIPTED_FOUNDER_REPLIES = INTERVIEW_SCRIPT.filter((turn) => turn.founder).length;

/** Beat 11: one wait/type/send triplet per scripted founder reply. */
function interviewSteps(): DemoStep[] {
  const steps: DemoStep[] = [];
  INTERVIEW_SCRIPT.forEach((turn, i) => {
    if (!turn.founder) return;
    const first = steps.length === 0;
    steps.push({
      id: `b11-wait-ai-${i}`,
      beat: 11,
      // Beat entry: jumping here lands on the founder chat, candidacy done.
      ...(first
        ? {
            route: interview,
            checkpoint: "candidacy-complete" as ScenarioId,
            caption: "The interview asks only what the memo could not source.",
          }
        : {}),
      action: { kind: "wait" },
      // The greeting/next question must have finished streaming into the store.
      waitFor: () => interviewerCount() >= i + 1,
      timeoutMs: 30_000,
      dwellMs: 1_000, // settle delay after the stream completes
    });
    steps.push({
      id: `b11-type-${i}`,
      beat: 11,
      action: { kind: "type", target: "chat-input", text: turn.founder, cps: 34 },
      dwellMs: 300,
    });
    steps.push({
      id: `b11-send-${i}`,
      beat: 11,
      action: { kind: "click", target: "btn-chat-send" },
      dwellMs: 500,
    });
  });
  return steps;
}

export const DEMO_STEPS: DemoStep[] = [
  // ----- Act 1 · B1 · Login ------------------------------------------------
  {
    id: "b1-login",
    beat: 1,
    route: () => "/login",
    checkpoint: "initial",
    action: { kind: "navigate" },
    caption: "Founders apply to funds. We inverted it.",
    interstitial: {
      act: "Act 1",
      title: "The investor",
      sub: "A thesis goes hunting for founders.",
    },
    dwellMs: 2_400,
  },
  {
    id: "b1-submit",
    beat: 1,
    action: { kind: "click", target: "login-submit" },
    dwellMs: 900,
  },

  // ----- B2 · Thesis intake ------------------------------------------------
  {
    id: "b2-thesis",
    beat: 2,
    route: () => "/thesis",
    checkpoint: "initial",
    action: { kind: "navigate" },
    caption: "Start with the thesis. A PDF or a link is enough.",
    dwellMs: 2_200,
  },
  {
    id: "b2-link",
    beat: 2,
    action: {
      kind: "type",
      target: "thesis-link-input",
      text: "https://fund.example/investment-thesis",
      cps: 30,
    },
    dwellMs: 400,
  },
  { id: "b2-read", beat: 2, action: { kind: "click", target: "btn-thesis-read" }, dwellMs: 400 },
  {
    id: "b2-wait-review",
    beat: 2,
    action: { kind: "wait" },
    waitFor: () => getDB().thesisIntake.stage === "review",
    timeoutMs: 10_000,
    caption: "We read what we can. The red fields need committee input.",
    dwellMs: 1_600,
  },
  {
    id: "b2-check-min",
    beat: 2,
    action: { kind: "type", target: "thesis-field-check-min", text: "250000", cps: 20 },
    dwellMs: 300,
  },
  {
    id: "b2-check-max",
    beat: 2,
    action: { kind: "type", target: "thesis-field-check-max", text: "1000000", cps: 20 },
    dwellMs: 300,
  },
  {
    id: "b2-no-vc",
    beat: 2,
    action: { kind: "click", target: "thesis-field-no-prior-vc" },
    dwellMs: 400,
  },
  {
    id: "b2-oss",
    beat: 2,
    action: { kind: "click", target: "thesis-field-corporate-oss" },
    dwellMs: 400,
  },
  { id: "b2-save", beat: 2, action: { kind: "click", target: "btn-thesis-save" }, dwellMs: 1_800 },

  // ----- B3 · Ranking ------------------------------------------------------
  {
    id: "b3-ranking",
    beat: 3,
    route: ranking,
    checkpoint: "thesis-ready",
    action: { kind: "navigate" },
    caption: "Eleven ventures found, scored, and ranked. Nobody applied.",
    dwellMs: 2_000,
  },
  { id: "b3-scroll-down", beat: 3, action: { kind: "scroll", to: "bottom" }, dwellMs: 1_800 },
  { id: "b3-scroll-up", beat: 3, action: { kind: "scroll", to: "top" }, dwellMs: 1_000 },

  // ----- B4 · Semantic query ----------------------------------------------
  {
    id: "b4-query",
    beat: 4,
    route: ranking,
    checkpoint: "thesis-ready",
    action: {
      kind: "type",
      target: "query-text",
      text: "tactile sensing for warehouse robot arms",
      cps: 30,
    },
    caption: "Ask the pool anything. Structured filters plus a semantic prompt.",
    dwellMs: 3_400,
  },
  { id: "b4-clear", beat: 4, action: { kind: "click", target: "query-clear" }, dwellMs: 1_000 },

  // ----- B5 · GraspLab memo ------------------------------------------------
  {
    id: "b5-open-grasplab",
    beat: 5,
    route: ranking,
    checkpoint: "thesis-ready",
    action: { kind: "click", target: `venture-row-${GRASPLAB_ID}` },
    caption: "The memo: every claim cited, every gap admitted. No hallucinated conviction.",
    dwellMs: 2_200,
  },
  { id: "b5-open-evidence", beat: 5, action: { kind: "click", target: "evidence-chip" }, dwellMs: 2_800 },
  { id: "b5-close-evidence", beat: 5, action: { kind: "key", key: "Escape" }, dwellMs: 700 },
  { id: "b5-spot-gaps", beat: 5, action: { kind: "spotlight", target: "memo-gaps" }, dwellMs: 3_200 },

  // ----- B6 · Weights behind the gear -------------------------------------
  {
    id: "b6-ranking",
    beat: 6,
    route: ranking,
    checkpoint: "thesis-ready",
    action: { kind: "navigate" },
    caption: "Scoring defaults are sensible. The settings are there when you disagree.",
    dwellMs: 1_400,
  },
  { id: "b6-gear", beat: 6, action: { kind: "click", target: "btn-open-weights" }, dwellMs: 1_400 },
  {
    id: "b6-slider",
    beat: 6,
    action: { kind: "slider", target: "slider-prior_collaboration", to: 0.2 },
    caption: "One slider and GraspLab takes the lead.",
    dwellMs: 2_800,
  },
  { id: "b6-close", beat: 6, action: { kind: "key", key: "Escape" }, dwellMs: 1_400 },

  // ----- B7 · Schedule the AI interview (the send happens live) ------------
  {
    id: "b7-open-grasplab",
    beat: 7,
    route: ranking,
    checkpoint: "thesis-ready",
    action: { kind: "click", target: `venture-row-${GRASPLAB_ID}` },
    caption: "We choose GraspLab and schedule the AI interview.",
    dwellMs: 1_800,
  },
  { id: "b7-send", beat: 7, action: { kind: "click", target: "btn-send-outreach" }, dwellMs: 2_000 },
  { id: "b7-confirm", beat: 7, action: { kind: "click", target: "btn-confirm-send" }, dwellMs: 3_800 },

  // ----- Act 2 · B8 · The invitation --------------------------------------
  {
    id: "b8-flip",
    beat: 8,
    route: interview,
    checkpoint: "outreach-sent",
    action: { kind: "wait" },
    caption: "Lena opens a personal invitation, not a form.",
    interstitial: {
      act: "Act 2",
      title: "The founder",
      sub: "Lena Fischer gets chosen.",
    },
    dwellMs: 1_600,
  },
  { id: "b8-founder-link", beat: 8, action: { kind: "navigate" }, route: interview, dwellMs: 2_200 },

  // ----- B9 · Consent ------------------------------------------------------
  {
    id: "b9-agree",
    beat: 9,
    route: interview,
    checkpoint: "outreach-sent",
    action: { kind: "click", target: "consent-agree" },
    caption: "She sees everything we hold and where it came from. Consent first.",
    dwellMs: 1_400,
  },
  { id: "b9-continue", beat: 9, action: { kind: "click", target: "btn-consent-continue" }, dwellMs: 1_800 },

  // ----- B10 · Candidacy (file drops are presenter-only) -------------------
  {
    id: "b10-linkedin",
    beat: 10,
    route: interview,
    checkpoint: "consented",
    action: {
      kind: "type",
      target: "candidacy-linkedin",
      text: "https://www.linkedin.com/in/lena-fischer-robotics",
      cps: 28,
    },
    caption: "Already chosen. She only completes her candidacy.",
    dwellMs: 500,
  },
  {
    id: "b10-traction",
    beat: 10,
    action: {
      kind: "type",
      target: "candidacy-traction",
      text: "3 paid warehouse pilots since April. Design-partner waitlist: 41 companies.",
      cps: 28,
    },
    dwellMs: 800,
  },
  { id: "b10-continue", beat: 10, action: { kind: "click", target: "btn-continue-interview" }, dwellMs: 1_400 },

  // ----- B11 · Interview (generated from INTERVIEW_SCRIPT) -----------------
  ...interviewSteps(),

  // ----- B12 · Interview done ----------------------------------------------
  {
    id: "b12-wait-final",
    beat: 12,
    route: interview,
    checkpoint: "candidacy-complete",
    action: { kind: "wait" },
    caption: "Ten minutes, no pitch theatre.",
    // The closing interviewer turn must have streamed fully.
    waitFor: () => interviewerCount() >= INTERVIEW_SCRIPT.length,
    timeoutMs: 30_000,
    dwellMs: 1_600,
  },
  { id: "b12-done", beat: 12, action: { kind: "click", target: "btn-interview-done" }, dwellMs: 2_800 },

  // ----- Act 3 · B13 · The board moved -------------------------------------
  {
    id: "b13-board",
    beat: 13,
    route: outreach,
    checkpoint: "interview-done",
    action: { kind: "navigate" },
    caption: "The board has already moved.",
    interstitial: {
      act: "Act 3",
      title: "Back to the investor",
      sub: "The evidence comes home.",
    },
    dwellMs: 1_400,
  },
  {
    id: "b13-spot-card",
    beat: 13,
    action: { kind: "spotlight", target: `outreach-card-${GRASPLAB_ID}` },
    dwellMs: 3_000,
  },

  // ----- B14 · Re-scored memo + follow-up ----------------------------------
  {
    id: "b14-venture",
    beat: 14,
    route: venture,
    checkpoint: "interview-done",
    action: { kind: "navigate" },
    caption: "Re-scored based on her own words, with consent on record. Traction 46 to 71.",
    dwellMs: 2_000,
  },
  {
    id: "b14-spot-toggle",
    beat: 14,
    action: { kind: "spotlight", target: "memo-version-toggle" },
    dwellMs: 1_600,
  },
  { id: "b14-toggle-pre", beat: 14, action: { kind: "click", target: "memo-version-toggle" }, dwellMs: 2_200 },
  { id: "b14-toggle-post", beat: 14, action: { kind: "click", target: "memo-version-toggle" }, dwellMs: 2_000 },
  {
    id: "b14-followup-type",
    beat: 14,
    action: {
      kind: "type",
      target: "followup-input",
      text: "Which pilots decide in December, and can we see the conversion terms before then?",
      cps: 32,
    },
    caption: "The investment team follows up right in the transcript.",
    dwellMs: 300,
  },
  { id: "b14-followup-send", beat: 14, action: { kind: "click", target: "btn-followup-send" }, dwellMs: 600 },
  {
    id: "b14-followup-reply",
    beat: 14,
    action: { kind: "wait" },
    // The scripted founder reply lands as one more founder message.
    waitFor: () => founderCount() > SCRIPTED_FOUNDER_REPLIES,
    timeoutMs: 15_000,
    dwellMs: 2_800,
  },

  // ----- B15 · Investment kickoff ------------------------------------------
  {
    id: "b15-invest",
    beat: 15,
    route: venture,
    checkpoint: "interview-done",
    action: { kind: "click", target: "btn-start-investment" },
    caption: "And when the team is convinced, the process starts here.",
    dwellMs: 1_600,
  },
  { id: "b15-board", beat: 15, action: { kind: "navigate" }, route: outreach, dwellMs: 1_200 },
  {
    id: "b15-spot-investment",
    beat: 15,
    action: { kind: "spotlight", target: `investment-card-${GRASPLAB_ID}` },
    caption: "She never applied. She got chosen.",
    dwellMs: 5_000,
  },
];

/** Index of the first step of a beat (every beat has at least one step). */
export function firstStepIndexOfBeat(beat: number): number {
  const index = DEMO_STEPS.findIndex((s) => s.beat === beat);
  return index === -1 ? 0 : index;
}

/** Entry route for a beat jump: first routed step of the beat, else "/login". */
export function beatEntryRoute(beat: number, ctx: DemoCtx): string {
  const step = DEMO_STEPS.find((s) => s.beat === beat && s.route);
  return step?.route ? step.route(ctx) : "/login";
}

/** Caption shown right after jumping to a beat (its first captioned step). */
export function beatCaption(beat: number): string | null {
  const step = DEMO_STEPS.find((s) => s.beat === beat && s.caption);
  return step?.caption ?? null;
}

/** Checkpoint at-or-before a beat (defensive for out-of-range values). */
export function beatCheckpoint(beat: number): ScenarioId {
  const clamped = Math.min(Math.max(Math.round(beat), 1), BEAT_COUNT);
  return BEAT_CHECKPOINT[clamped] ?? "initial";
}
