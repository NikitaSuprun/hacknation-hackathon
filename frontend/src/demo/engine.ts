/**
 * Track E — the demo autopilot engine.
 *
 * Executes DEMO_STEPS against the live DOM by dispatching synthetic events at
 * `[data-demo-id]` targets, so autopilot exercises the exact code paths a
 * hand-driven demo would. Every dependency on other tracks is defensive:
 * targets are polled (up to 5s), and a miss stalls quietly with a toast —
 * never a hang, never a throw.
 *
 * Checkpoints (mocks/scenarios) are applied only on JUMPS (prev/next/scrubber/
 * ?beat= deep links). Continuous play produces each state organically through
 * the UI itself — including the beat-5 weight change, which a checkpoint
 * replay would wipe.
 */
import { useSyncExternalStore } from "react";
import type { NavigateFunction } from "react-router-dom";
import { toast } from "sonner";
import { applyScenario } from "@/mocks/scenarios";
import { getDB, resetDB, subscribe as subscribeDB } from "@/mocks/state";
import { setMockLatencyDisabled } from "@/lib/data/MockDataSource";
import { dataSource } from "@/lib/data";
import {
  BEAT_COUNT,
  DEMO_STEPS,
  FALLBACK_THESIS_ID,
  beatCaption,
  beatCheckpoint,
  beatEntryRoute,
  firstStepIndexOfBeat,
} from "@/demo/script";
import { SPEEDS } from "@/demo/types";
import type { DemoCtx, DemoStep, EngineState } from "@/demo/types";

type PollResult = "ok" | "timeout" | "cancelled";

const DEFAULT_TIMEOUT_MS = 5_000;
const DEFAULT_DWELL_MS = 400;

const INITIAL_STATE: EngineState = {
  status: "idle",
  stepIndex: 0,
  beat: 1,
  caption: null,
  captionsOn: true,
  speed: 1,
  hudVisible: false,
  spotlight: null,
  stalledStepId: null,
};

function isEditable(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || target.isContentEditable;
}

function demoSelector(id: string): string {
  return `[data-demo-id="${id}"]`;
}

const sleep = (ms: number) =>
  new Promise<void>((resolve) => setTimeout(resolve, Math.max(0, ms)));

// --- Synthetic DOM interaction (all events have isTrusted === false, which is
// --- exactly how the auto-pause listener tells them apart from the presenter).

function pointerInit(el: Element): PointerEventInit & MouseEventInit {
  const rect = el.getBoundingClientRect();
  return {
    bubbles: true,
    cancelable: true,
    composed: true,
    view: window,
    clientX: rect.left + rect.width / 2,
    clientY: rect.top + rect.height / 2,
    button: 0,
    buttons: 1,
    pointerId: 7331,
    pointerType: "mouse",
    isPrimary: true,
  };
}

function dispatchSyntheticClick(el: HTMLElement): void {
  const init = pointerInit(el);
  const hasPointer = typeof PointerEvent !== "undefined";
  if (hasPointer) el.dispatchEvent(new PointerEvent("pointerover", init));
  el.dispatchEvent(new MouseEvent("mouseover", init));
  if (hasPointer) el.dispatchEvent(new PointerEvent("pointerdown", init));
  el.dispatchEvent(new MouseEvent("mousedown", init));
  if (typeof el.focus === "function") el.focus();
  if (hasPointer) el.dispatchEvent(new PointerEvent("pointerup", { ...init, buttons: 0 }));
  el.dispatchEvent(new MouseEvent("mouseup", { ...init, buttons: 0 }));
  // Untrusted click events still run activation behavior (form submit etc.).
  el.dispatchEvent(new MouseEvent("click", { ...init, buttons: 0, detail: 1 }));
}

function dispatchKeyOn(el: HTMLElement, key: string): void {
  const init: KeyboardEventInit = { key, code: key, bubbles: true, cancelable: true, composed: true };
  el.dispatchEvent(new KeyboardEvent("keydown", init));
  el.dispatchEvent(new KeyboardEvent("keyup", init));
}

/** React-safe programmatic value set: prototype setter + bubbling InputEvent. */
function setNativeValue(el: HTMLInputElement | HTMLTextAreaElement, value: string, data: string): void {
  const proto =
    el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  const setter = Object.getOwnPropertyDescriptor(proto, "value")?.set;
  if (setter) setter.call(el, value);
  else el.value = value;
  el.dispatchEvent(new InputEvent("input", { bubbles: true, data, inputType: "insertText" }));
}

export class DemoEngine {
  private state: EngineState = INITIAL_STATE;
  private readonly listeners = new Set<() => void>();
  /** Cancellation token — every pause/jump bumps it; stale loops exit quietly. */
  private gen = 0;
  private armed = false;
  private navigateFn: NavigateFunction | null = null;
  /** Query string (minus beat=) re-attached to every engine navigation. */
  private search = "";
  private ctx: DemoCtx = { thesisId: FALLBACK_THESIS_ID };
  private ctxPromise: Promise<DemoCtx> | null = null;

  // --- external store (React reads via useEngineState) ---

  readonly getState = (): EngineState => this.state;

  readonly subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };

  private setState(patch: Partial<EngineState>): void {
    this.state = { ...this.state, ...patch };
    for (const listener of this.listeners) listener();
  }

  // --- lifecycle ---

  setNavigate(fn: NavigateFunction): void {
    this.navigateFn = fn;
  }

  arm(opts: { autopilot: boolean; beat?: number }): void {
    if (this.armed) return;
    this.armed = true;
    const params = new URLSearchParams(window.location.search);
    params.delete("beat"); // a refresh mid-demo must not re-jump to a stale beat
    const qs = params.toString();
    this.search = qs ? `?${qs}` : "";
    window.addEventListener("keydown", this.onKeyDown, true);
    window.addEventListener("pointerdown", this.onPointerDown, true);
    this.setState({ status: "paused", hudVisible: opts.autopilot });
    void this.ensureCtx();
    if (opts.beat) void this.gotoBeat(opts.beat);
  }

  disarm(): void {
    if (!this.armed) return;
    this.armed = false;
    this.gen += 1;
    setMockLatencyDisabled(false);
    window.removeEventListener("keydown", this.onKeyDown, true);
    window.removeEventListener("pointerdown", this.onPointerDown, true);
  }

  /** Thesis id resolved once via the data source (fixture id as fallback). */
  private ensureCtx(): Promise<DemoCtx> {
    this.ctxPromise ??= (async () => {
      try {
        const theses = await dataSource().listTheses();
        const id = theses[0]?.thesis_id;
        if (id) this.ctx = { thesisId: id };
      } catch {
        try {
          this.ctx = { thesisId: getDB().thesis.thesis_id };
        } catch {
          /* keep FALLBACK_THESIS_ID */
        }
      }
      return this.ctx;
    })();
    return this.ctxPromise;
  }

  // --- transport controls ---

  play(): void {
    if (this.state.status === "playing" || this.state.status === "done") return;
    if (this.state.stepIndex >= DEMO_STEPS.length) {
      this.finish();
      return;
    }
    this.gen += 1;
    setMockLatencyDisabled(true);
    this.setState({ status: "playing", stalledStepId: null });
    void this.runLoop(this.gen);
  }

  pause(): void {
    if (this.state.status !== "playing" && this.state.status !== "stalled") return;
    this.gen += 1;
    setMockLatencyDisabled(false);
    this.setState({ status: "paused", stalledStepId: null });
  }

  togglePlay(): void {
    if (this.state.status === "playing") this.pause();
    else this.play();
  }

  nextBeat(): void {
    void this.gotoBeat(Math.min(this.state.beat + 1, BEAT_COUNT));
  }

  prevBeat(): void {
    void this.gotoBeat(Math.max(this.state.beat - 1, 1));
  }

  /** Scrubber/arrow jump: checkpoint at-or-before the beat + entry route, paused. */
  async gotoBeat(rawBeat: number): Promise<void> {
    const beat = Math.min(Math.max(Math.round(rawBeat), 1), BEAT_COUNT);
    this.gen += 1;
    setMockLatencyDisabled(false);
    await this.ensureCtx();
    try {
      applyScenario(beatCheckpoint(beat));
    } catch {
      /* never let a fixture problem take down the HUD */
    }
    this.navigateTo(beatEntryRoute(beat, this.ctx));
    this.setState({
      status: "paused",
      stepIndex: firstStepIndexOfBeat(beat),
      beat,
      caption: beatCaption(beat),
      spotlight: null,
      stalledStepId: null,
    });
  }

  /** Shift+R — full reset: seed DB, back to /login, engine to step 0, paused. */
  reset(): void {
    this.gen += 1;
    setMockLatencyDisabled(false);
    try {
      resetDB();
    } catch {
      /* defensive */
    }
    this.navigateTo("/login");
    this.setState({
      status: "paused",
      stepIndex: 0,
      beat: 1,
      caption: null,
      spotlight: null,
      stalledStepId: null,
    });
  }

  cycleSpeed(): void {
    const i = SPEEDS.indexOf(this.state.speed);
    this.setState({ speed: SPEEDS[(i + 1) % SPEEDS.length] });
  }

  toggleCaptions(): void {
    this.setState({ captionsOn: !this.state.captionsOn });
  }

  toggleHud(): void {
    this.setState({ hudVisible: !this.state.hudVisible });
  }

  // --- global input (trusted events only — synthetic ones are ours) ---

  private readonly onKeyDown = (e: KeyboardEvent): void => {
    if (!e.isTrusted) return;
    if ((e.ctrlKey || e.metaKey) && e.key === ".") {
      e.preventDefault();
      this.toggleHud();
      return;
    }
    const editable = isEditable(e.target);
    if (e.shiftKey && (e.key === "R" || e.key === "r") && !editable) {
      e.preventDefault();
      this.reset();
      return;
    }
    if ((e.key === " " || e.code === "Space") && !editable) {
      e.preventDefault();
      this.togglePlay();
      return;
    }
    // Arrows always work while the show is running (skip a stalled beat even
    // when autopilot left focus inside an input); otherwise respect editing.
    const engaged = this.state.status === "playing" || this.state.status === "stalled";
    if (e.key === "ArrowRight" && (engaged || !editable)) {
      e.preventDefault();
      this.nextBeat();
      return;
    }
    if (e.key === "ArrowLeft" && (engaged || !editable)) {
      e.preventDefault();
      this.prevBeat();
    }
  };

  /** Any REAL pointerdown outside the HUD while playing → the presenter takes over. */
  private readonly onPointerDown = (e: PointerEvent): void => {
    if (!e.isTrusted) return;
    if (this.state.status !== "playing") return;
    const target = e.target instanceof Element ? e.target : null;
    if (target?.closest("[data-demo-hud]")) return;
    this.pause();
  };

  // --- the run loop ---

  private async runLoop(gen: number): Promise<void> {
    await this.ensureCtx();
    if (gen !== this.gen) return;
    while (gen === this.gen && this.state.status === "playing") {
      const index = this.state.stepIndex;
      if (index >= DEMO_STEPS.length) {
        this.finish();
        return;
      }
      const step = DEMO_STEPS[index];
      this.setState({ beat: step.beat, ...(step.caption ? { caption: step.caption } : {}) });
      let ok = false;
      try {
        ok = await this.execStep(step, gen);
      } catch {
        ok = false; // never throw out of the loop
      }
      if (gen !== this.gen) return;
      if (!ok) {
        this.stall(step);
        return;
      }
      await sleep((step.dwellMs ?? DEFAULT_DWELL_MS) / this.state.speed);
      if (gen !== this.gen) return;
      this.setState({ stepIndex: index + 1 });
    }
  }

  private finish(): void {
    this.gen += 1;
    setMockLatencyDisabled(false);
    this.setState({ status: "done", stepIndex: DEMO_STEPS.length, stalledStepId: null });
  }

  private stall(step: DemoStep): void {
    this.gen += 1;
    setMockLatencyDisabled(false);
    this.setState({ status: "stalled", stalledStepId: step.id });
    toast(`Demo stalled at ${step.id} — → to skip`);
  }

  /** Poll a predicate; resolves on the store's subscribe() too, so transcript
   *  growth is noticed the instant the mock emits it. */
  private pollUntil(pred: () => boolean, timeoutMs: number, gen: number): Promise<PollResult> {
    return new Promise((resolve) => {
      let settled = false;
      let cleanup = () => {};
      const finish = (result: PollResult) => {
        if (settled) return;
        settled = true;
        cleanup();
        resolve(result);
      };
      const check = () => {
        if (gen !== this.gen) {
          finish("cancelled");
          return;
        }
        let hit = false;
        try {
          hit = pred();
        } catch {
          hit = false;
        }
        if (hit) finish("ok");
      };
      const interval = window.setInterval(check, 120);
      const unsubscribe = subscribeDB(check);
      const timer = window.setTimeout(() => {
        check();
        finish("timeout");
      }, timeoutMs);
      cleanup = () => {
        window.clearInterval(interval);
        window.clearTimeout(timer);
        unsubscribe();
      };
      check();
    });
  }

  private async findTarget(id: string, timeoutMs: number, gen: number): Promise<HTMLElement | null> {
    const result = await this.pollUntil(
      () => document.querySelector(demoSelector(id)) !== null,
      timeoutMs,
      gen,
    );
    if (result !== "ok") return null;
    return document.querySelector<HTMLElement>(demoSelector(id));
  }

  private navigateTo(path: string): void {
    this.setState({ spotlight: null });
    if (this.navigateFn) this.navigateFn({ pathname: path, search: this.search });
  }

  /** true = proceed, false = stall. Cancellation reads as true (loop exits on gen). */
  private async execStep(step: DemoStep, gen: number): Promise<boolean> {
    const timeout = step.timeoutMs ?? DEFAULT_TIMEOUT_MS;
    if (step.waitFor) {
      const result = await this.pollUntil(step.waitFor, timeout, gen);
      if (result === "cancelled") return true;
      if (result === "timeout") return false;
    }
    if (gen !== this.gen) return true;
    const action = step.action;
    switch (action.kind) {
      case "wait":
        return true;
      case "navigate": {
        if (!step.route) return true;
        this.navigateTo(step.route(this.ctx));
        await sleep(180); // let the route mount before the next lookup
        return true;
      }
      case "scenario": {
        applyScenario(action.id);
        return true;
      }
      case "scroll": {
        const doc = document.scrollingElement ?? document.documentElement;
        const top = action.to === "bottom" ? doc.scrollHeight - window.innerHeight : 0;
        window.scrollTo({ top: Math.max(0, top), behavior: "smooth" });
        return true;
      }
      case "spotlight": {
        if (action.target === null) {
          this.setState({ spotlight: null });
          return true;
        }
        const el = await this.findTarget(action.target, timeout, gen);
        if (gen !== this.gen) return true;
        if (!el) return false;
        el.scrollIntoView({ block: "center", behavior: "smooth" });
        this.setState({ spotlight: action.target });
        return true;
      }
      case "click": {
        const el = await this.findTarget(action.target, timeout, gen);
        if (gen !== this.gen) return true;
        if (!el) return false;
        el.scrollIntoView({ block: "center", behavior: "smooth" });
        await sleep(260);
        if (gen !== this.gen) return true;
        dispatchSyntheticClick(el);
        return true;
      }
      case "key": {
        const target =
          document.activeElement instanceof HTMLElement ? document.activeElement : document.body;
        dispatchKeyOn(target, action.key);
        return true;
      }
      case "type": {
        const host = await this.findTarget(action.target, timeout, gen);
        if (gen !== this.gen) return true;
        if (!host) return false;
        const field =
          host instanceof HTMLInputElement || host instanceof HTMLTextAreaElement
            ? host
            : host.querySelector<HTMLInputElement | HTMLTextAreaElement>("input, textarea");
        if (!field) return false;
        field.scrollIntoView({ block: "center", behavior: "smooth" });
        field.focus();
        const delay = 1000 / (action.cps ?? 28);
        for (let i = 0; i < action.text.length; i++) {
          if (gen !== this.gen) return true;
          setNativeValue(field, action.text.slice(0, i + 1), action.text[i]);
          await sleep(delay);
        }
        return true;
      }
      case "slider":
        return this.driveSlider(action.target, action.to, timeout, gen);
      default:
        return true;
    }
  }

  /** Radix slider via keyboard: focus the thumb, ArrowUp/Down until aria-valuenow lands. */
  private async driveSlider(
    target: string,
    to: number,
    timeoutMs: number,
    gen: number,
  ): Promise<boolean> {
    const root = await this.findTarget(target, timeoutMs, gen);
    if (gen !== this.gen) return true;
    if (!root) return false;
    const thumb = root.matches('[role="slider"]')
      ? root
      : root.querySelector<HTMLElement>('[role="slider"]');
    if (!thumb) return false;
    root.scrollIntoView({ block: "center", behavior: "smooth" });
    await sleep(200);
    if (gen !== this.gen) return true;
    thumb.focus();
    const read = () => parseFloat(thumb.getAttribute("aria-valuenow") ?? "NaN");
    const max = parseFloat(thumb.getAttribute("aria-valuemax") ?? "1");
    // Sliders may run 0–1 (weights) or 0–100 (percent display) — adapt.
    const scale = Number.isFinite(max) && max > 1.5 ? 100 : 1;
    const goal = to * scale;
    const epsilon = 0.004 * scale;
    let stuck = 0;
    for (let i = 0; i < 60; i++) {
      if (gen !== this.gen) return true;
      const value = read();
      if (!Number.isFinite(value)) break;
      if (Math.abs(value - goal) <= epsilon) break;
      dispatchKeyOn(thumb, value < goal ? "ArrowUp" : "ArrowDown");
      await sleep(70);
      const next = read();
      if (next === value) {
        stuck += 1;
        if (stuck >= 3) break; // slider isn't keyboard-driven — keep the show going
      } else {
        stuck = 0;
        // Crossed the goal — the step size overshoots the epsilon; stop here.
        if ((value < goal && next >= goal - epsilon) || (value > goal && next <= goal + epsilon)) break;
      }
    }
    return true;
  }
}

let singleton: DemoEngine | null = null;

export function getDemoEngine(): DemoEngine {
  singleton ??= new DemoEngine();
  return singleton;
}

/** React binding for the HUD and spotlight. */
export function useEngineState(engine: DemoEngine): EngineState {
  return useSyncExternalStore(engine.subscribe, engine.getState);
}
