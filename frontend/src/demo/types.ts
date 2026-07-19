/**
 * Track E, demo autopilot type surface.
 *
 * The whole scripted demo is data: an ordered list of DemoStep, each belonging
 * to one of 14 beats. The engine executes steps against the *real* UI by
 * dispatching synthetic DOM events at `[data-demo-id]` targets, so autopilot
 * exercises exactly the code paths a hand-driven demo would.
 */
import type { ScenarioId } from "@/mocks/scenarios";

/** Runtime context resolved once at engine start. */
export interface DemoCtx {
  thesisId: string;
}

export type StepAction =
  /** Navigate to the step's `route(ctx)` via react-router. */
  | { kind: "navigate" }
  /** Full synthetic pointer sequence + click on `[data-demo-id=target]`. */
  | { kind: "click"; target: string }
  /** Character-by-character typing (native value setter + InputEvent). */
  | { kind: "type"; target: string; text: string; cps?: number }
  /** Keyboard event dispatched at the active element (bubbles to document). */
  | { kind: "key"; key: string }
  /** Drive a radix slider to a value via ArrowUp/ArrowDown on its thumb. */
  | { kind: "slider"; target: string; to: number }
  /** Jump the mock store to a named checkpoint. */
  | { kind: "scenario"; id: ScenarioId }
  /** One-off smooth window scroll (presentational, not scroll-linked). */
  | { kind: "scroll"; to: "top" | "bottom" }
  /** Move the spotlight ring onto a target (null clears it). */
  | { kind: "spotlight"; target: string | null }
  /** Nothing but caption/waitFor/dwell. */
  | { kind: "wait" };

export interface DemoStep {
  /** Stable id, shown in the stall toast ("Demo stalled at b4-open-evidence"). */
  id: string;
  /** 1..14, the beat this step belongs to. */
  beat: number;
  /**
   * Route for `navigate` actions; on the FIRST step of a beat it also defines
   * the beat's entry route used by prev/next/scrubber jumps.
   */
  route?: (ctx: DemoCtx) => string;
  /**
   * Checkpoint the mock store must be in when JUMPING to this beat.
   * Only read on beat-entry steps; continuous play never re-applies it
   * (live actions produce the state organically).
   */
  checkpoint?: ScenarioId;
  action: StepAction;
  /** Pause after the action completes (divided by the speed factor). */
  dwellMs?: number;
  /** Shown in the HUD caption strip for the rest of the beat. */
  caption?: string;
  /** Polled before the action runs; timeout → quiet stall (never a hang). */
  waitFor?: () => boolean;
  /** Poll budget for waitFor/target lookup. Default 5000ms. */
  timeoutMs?: number;
  /**
   * Centered act announcement shown BEFORE this step's action, so the room
   * knows whose perspective the demo is about to show.
   */
  interstitial?: { act: string; title: string; sub: string };
}

export type EngineStatus = "idle" | "playing" | "paused" | "stalled" | "done";

export const SPEEDS = [1, 1.5, 2] as const;
export type Speed = (typeof SPEEDS)[number];

export interface EngineState {
  status: EngineStatus;
  /** Index of the NEXT step to execute. */
  stepIndex: number;
  /** Current beat, 1..14. */
  beat: number;
  caption: string | null;
  captionsOn: boolean;
  speed: Speed;
  hudVisible: boolean;
  /** data-demo-id the spotlight ring should hug, or null. */
  spotlight: string | null;
  /** Step id the engine stalled on (target/waitFor timeout), for the HUD. */
  stalledStepId: string | null;
  /** Centered act announcement currently on screen, or null. */
  interstitial: { act: string; title: string; sub: string } | null;
}
