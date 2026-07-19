/**
 * Track E — the 14-beat demo script as data.
 *
 * Beats 1–6 are the partner side (login → thesis → ranking → memo → weights →
 * outreach send); 7–11 the founder side (consent → candidacy → interview);
 * 12–14 the payoff (board moved, memo re-scored, final ranking).
 *
 * The interview beat (B10) is generated from INTERVIEW_SCRIPT so a longer
 * Track-A script expands the autopilot automatically.
 */
import { getDB } from "@/mocks/state";
import { GRASPLAB_ID } from "@/mocks/fixtures/seed";
import { INTERVIEW_SCRIPT } from "@/mocks/fixtures/chatScript";
import type { ScenarioId } from "@/mocks/scenarios";
import type { DemoCtx, DemoStep } from "@/demo/types";

export const BEAT_COUNT = 14;

/**
 * Fallback thesis id (the generated fixture). The engine resolves the real id
 * via dataSource().listTheses() at start; this only papers over a failure.
 */
export const FALLBACK_THESIS_ID = "aaaaaaaa-0000-4000-8000-000000000001";

/** State the mock store is put into when JUMPING to a beat (never during continuous play). */
export const BEAT_CHECKPOINT: Record<number, ScenarioId> = {
  1: "initial",
  2: "initial",
  3: "initial",
  4: "initial",
  5: "initial",
  6: "initial", // the send happens IN beat 6
  7: "outreach-sent",
  8: "outreach-sent",
  9: "consented",
  10: "candidacy-complete",
  11: "candidacy-complete",
  12: "interview-done",
  13: "interview-done",
  14: "interview-done",
};

const ranking = (ctx: DemoCtx) => `/t/${ctx.thesisId}/ranking`;
const weights = (ctx: DemoCtx) => `/t/${ctx.thesisId}/weights`;
const outreach = (ctx: DemoCtx) => `/t/${ctx.thesisId}/outreach`;
const venture = (ctx: DemoCtx) => `/t/${ctx.thesisId}/venture/${GRASPLAB_ID}`;
const interview = () => "/interview/demo";

/** Interviewer messages that have fully landed in the mock transcript. */
function interviewerCount(): number {
  return getDB().interview.transcript.filter((m) => m.role === "interviewer").length;
}

/** Beat 10 — one wait/type/send triplet per scripted founder reply. */
function interviewSteps(): DemoStep[] {
  const steps: DemoStep[] = [];
  INTERVIEW_SCRIPT.forEach((turn, i) => {
    if (!turn.founder) return;
    const first = steps.length === 0;
    steps.push({
      id: `b10-wait-ai-${i}`,
      beat: 10,
      // Beat entry: jumping here lands on the founder chat, candidacy done.
      ...(first
        ? {
            route: interview,
            checkpoint: "candidacy-complete" as ScenarioId,
            caption: "The interview asks only what the memo couldn't source.",
          }
        : {}),
      action: { kind: "wait" },
      // The greeting/next question must have finished streaming into the store.
      waitFor: () => interviewerCount() >= i + 1,
      timeoutMs: 30_000,
      dwellMs: 1_000, // settle delay after the stream completes
    });
    steps.push({
      id: `b10-type-${i}`,
      beat: 10,
      action: { kind: "type", target: "chat-input", text: turn.founder, cps: 34 },
      dwellMs: 300,
    });
    steps.push({
      id: `b10-send-${i}`,
      beat: 10,
      action: { kind: "click", target: "btn-chat-send" },
      dwellMs: 500,
    });
  });
  return steps;
}

export const DEMO_STEPS: DemoStep[] = [
  // ——— B1 · Login ————————————————————————————————————————————————
  {
    id: "b1-login",
    beat: 1,
    route: () => "/login",
    checkpoint: "initial",
    action: { kind: "navigate" },
    caption: "Founders apply to funds. We inverted it.",
    dwellMs: 2_400,
  },
  {
    id: "b1-submit",
    beat: 1,
    action: { kind: "click", target: "login-submit" },
    dwellMs: 900,
  },

  // ——— B2 · Thesis ———————————————————————————————————————————————
  {
    id: "b2-thesis",
    beat: 2,
    route: () => "/thesis",
    checkpoint: "initial",
    action: { kind: "navigate" },
    caption: "One thesis. The system watches GitHub, arXiv, and the Swiss registry.",
    dwellMs: 4_600,
  },

  // ——— B3 · Ranking ——————————————————————————————————————————————
  {
    id: "b3-ranking",
    beat: 3,
    route: ranking,
    checkpoint: "initial",
    action: { kind: "navigate" },
    caption: "Every venture here was found, not submitted.",
    dwellMs: 2_000,
  },
  { id: "b3-scroll-down", beat: 3, action: { kind: "scroll", to: "bottom" }, dwellMs: 1_800 },
  { id: "b3-scroll-up", beat: 3, action: { kind: "scroll", to: "top" }, dwellMs: 1_000 },

  // ——— B4 · GraspLab memo ————————————————————————————————————————
  {
    id: "b4-open-grasplab",
    beat: 4,
    route: ranking,
    checkpoint: "initial",
    action: { kind: "click", target: `venture-row-${GRASPLAB_ID}` },
    caption: "Every claim cited — and here's what we don't know. No hallucinated conviction.",
    dwellMs: 2_200,
  },
  { id: "b4-open-evidence", beat: 4, action: { kind: "click", target: "evidence-chip" }, dwellMs: 2_800 },
  { id: "b4-close-evidence", beat: 4, action: { kind: "key", key: "Escape" }, dwellMs: 700 },
  { id: "b4-spot-gaps", beat: 4, action: { kind: "spotlight", target: "memo-gaps" }, dwellMs: 3_200 },

  // ——— B5 · Weights ——————————————————————————————————————————————
  {
    id: "b5-weights",
    beat: 5,
    route: weights,
    checkpoint: "initial",
    action: { kind: "navigate" },
    caption: "One slider — instant re-rank. GraspLab takes #1.",
    dwellMs: 1_800,
  },
  {
    id: "b5-slider",
    beat: 5,
    action: { kind: "slider", target: "slider-prior_collaboration", to: 0.2 },
    dwellMs: 3_000,
  },

  // ——— B6 · Choose GraspLab (the send happens live) ———————————————
  {
    id: "b6-ranking",
    beat: 6,
    route: ranking,
    checkpoint: "initial",
    action: { kind: "navigate" },
    caption: "We choose GraspLab. The email says exactly why — provenance and opt-out included.",
    dwellMs: 1_600,
  },
  {
    id: "b6-open-grasplab",
    beat: 6,
    action: { kind: "click", target: `venture-row-${GRASPLAB_ID}` },
    dwellMs: 1_600,
  },
  { id: "b6-send", beat: 6, action: { kind: "click", target: "btn-send-outreach" }, dwellMs: 2_000 },
  { id: "b6-confirm", beat: 6, action: { kind: "click", target: "btn-confirm-send" }, dwellMs: 3_800 },

  // ——— B7 · Persona flip ——————————————————————————————————————————
  {
    id: "b7-flip",
    beat: 7,
    route: interview,
    checkpoint: "outreach-sent",
    action: { kind: "wait" },
    caption: "Now the other side.",
    dwellMs: 1_600,
  },
  { id: "b7-founder-link", beat: 7, action: { kind: "navigate" }, route: interview, dwellMs: 2_200 },

  // ——— B8 · Consent ——————————————————————————————————————————————
  {
    id: "b8-agree",
    beat: 8,
    route: interview,
    checkpoint: "outreach-sent",
    action: { kind: "click", target: "consent-agree" },
    caption: "Lena sees everything we know and where it came from. Consent first, always.",
    dwellMs: 1_400,
  },
  { id: "b8-continue", beat: 8, action: { kind: "click", target: "btn-consent-continue" }, dwellMs: 1_800 },

  // ——— B9 · Candidacy (file drops are presenter-only — synthetic files can't drop) ———
  {
    id: "b9-linkedin",
    beat: 9,
    route: interview,
    checkpoint: "consented",
    action: {
      kind: "type",
      target: "candidacy-linkedin",
      text: "https://www.linkedin.com/in/lena-fischer-robotics",
      cps: 28,
    },
    caption: "She's already chosen — she's just completing her candidacy.",
    dwellMs: 500,
  },
  {
    id: "b9-traction",
    beat: 9,
    action: {
      kind: "type",
      target: "candidacy-traction",
      text: "3 paid warehouse pilots since April. Design-partner waitlist: 41 companies.",
      cps: 28,
    },
    dwellMs: 800,
  },
  { id: "b9-continue", beat: 9, action: { kind: "click", target: "btn-continue-interview" }, dwellMs: 1_400 },

  // ——— B10 · Interview (generated from INTERVIEW_SCRIPT) ——————————
  ...interviewSteps(),

  // ——— B11 · Interview done ———————————————————————————————————————
  {
    id: "b11-wait-final",
    beat: 11,
    route: interview,
    checkpoint: "candidacy-complete",
    action: { kind: "wait" },
    caption: "No pitch theatre.",
    // The closing interviewer turn must have streamed fully.
    waitFor: () => interviewerCount() >= INTERVIEW_SCRIPT.length,
    timeoutMs: 30_000,
    dwellMs: 1_600,
  },
  { id: "b11-done", beat: 11, action: { kind: "click", target: "btn-interview-done" }, dwellMs: 2_800 },

  // ——— B12 · Board moved ——————————————————————————————————————————
  {
    id: "b12-board",
    beat: 12,
    route: outreach,
    checkpoint: "interview-done",
    action: { kind: "navigate" },
    caption: "Back on the partner's board, the card has already moved.",
    dwellMs: 1_400,
  },
  {
    id: "b12-spot-card",
    beat: 12,
    action: { kind: "spotlight", target: `outreach-card-${GRASPLAB_ID}` },
    dwellMs: 3_400,
  },

  // ——— B13 · Re-scored memo ———————————————————————————————————————
  {
    id: "b13-venture",
    beat: 13,
    route: venture,
    checkpoint: "interview-done",
    action: { kind: "navigate" },
    caption:
      "Same memo, four minutes later. Traction 46 → 71, every new claim cited to her own words — with consent on record.",
    dwellMs: 2_000,
  },
  {
    id: "b13-spot-toggle",
    beat: 13,
    action: { kind: "spotlight", target: "memo-version-toggle" },
    dwellMs: 1_800,
  },
  { id: "b13-toggle-pre", beat: 13, action: { kind: "click", target: "memo-version-toggle" }, dwellMs: 2_400 },
  { id: "b13-toggle-post", beat: 13, action: { kind: "click", target: "memo-version-toggle" }, dwellMs: 2_400 },

  // ——— B14 · Payoff ———————————————————————————————————————————————
  {
    id: "b14-ranking",
    beat: 14,
    route: ranking,
    checkpoint: "interview-done",
    action: { kind: "navigate" },
    caption: "She never applied. She got chosen.",
    dwellMs: 6_000,
  },
];

/** Index of the first step of a beat (every beat has at least one step). */
export function firstStepIndexOfBeat(beat: number): number {
  const index = DEMO_STEPS.findIndex((s) => s.beat === beat);
  return index === -1 ? 0 : index;
}

/** Entry route for a beat jump — first routed step of the beat, else "/login". */
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
