/**
 * Track E — the autopilot HUD: a small floating bar, bottom-center, paper on a
 * hairline border, mono labels. Quiet and Swiss — it narrates, it never covers
 * the content being demonstrated. Everything inside is marked data-demo-hud so
 * presenter clicks here never trigger the auto-pause.
 */
import { useEffect } from "react";
import { ChevronLeft, ChevronRight, Pause, Play, RotateCcw } from "lucide-react";
import { cn } from "@/lib/utils";
import { useEngineState, type DemoEngine } from "@/demo/engine";
import { BEAT_COUNT } from "@/demo/script";

function HudButton({
  title,
  onClick,
  active,
  children,
  className,
}: {
  title: string;
  onClick: () => void;
  active?: boolean;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <button
      type="button"
      title={title}
      onClick={onClick}
      className={cn(
        "flex h-7 min-w-7 items-center justify-center rounded-ctrl px-1 text-ink transition-colors duration-120 ease-swift hover:bg-wash",
        active && "text-electric",
        className,
      )}
    >
      {children}
    </button>
  );
}

const STATUS_LABEL: Record<string, string> = {
  idle: "ready",
  paused: "paused",
  playing: "playing",
  stalled: "stalled",
  done: "done",
};

export function DemoHud({ engine }: { engine: DemoEngine }) {
  const state = useEngineState(engine);

  // Surfaces that own the bottom of the viewport (the interview composer)
  // reserve room for the bar while it is on screen — see index.css.
  useEffect(() => {
    if (!state.hudVisible) return;
    document.body.classList.add("demo-hud-active");
    return () => document.body.classList.remove("demo-hud-active");
  }, [state.hudVisible]);

  if (!state.hudVisible) return null;

  const playing = state.status === "playing";
  const beats = Array.from({ length: BEAT_COUNT }, (_, i) => i + 1);

  return (
    <div
      data-demo-hud
      // Left-aligned on wide screens so it never covers the interview
      // composer, which owns the centre column.
      className="pointer-events-none fixed inset-x-0 bottom-5 z-[100] flex flex-col items-center gap-2 px-4 xl:items-start xl:pl-6"
    >
      {state.captionsOn && state.caption && (
        <div className="pointer-events-auto max-w-xl rounded-ctrl border border-line bg-paper px-4 py-2 shadow-lift">
          <p className="text-center text-small leading-snug text-ink">{state.caption}</p>
        </div>
      )}

      <div className="pointer-events-auto flex items-center gap-1 rounded-ctrl border border-line bg-paper px-2 py-1.5 shadow-lift">
        <HudButton title="Reset (Shift+R)" onClick={() => engine.reset()}>
          <RotateCcw size={13} strokeWidth={1.75} />
        </HudButton>

        <HudButton title="Previous beat (←)" onClick={() => engine.prevBeat()}>
          <ChevronLeft size={15} strokeWidth={1.75} />
        </HudButton>

        <HudButton
          title={playing ? "Pause (Space)" : "Play (Space)"}
          onClick={() => engine.togglePlay()}
          active={playing}
        >
          {playing ? (
            <Pause size={14} strokeWidth={1.75} />
          ) : (
            <Play size={14} strokeWidth={1.75} />
          )}
        </HudButton>

        <HudButton title="Next beat (→)" onClick={() => engine.nextBeat()}>
          <ChevronRight size={15} strokeWidth={1.75} />
        </HudButton>

        <div className="mx-1 h-4 w-px bg-line" />

        <div className="flex items-center gap-[5px] px-1">
          {beats.map((n) => (
            <button
              key={n}
              type="button"
              title={`Beat ${n}`}
              onClick={() => void engine.gotoBeat(n)}
              className={cn(
                "h-2 w-2 rounded-full transition-colors duration-120 ease-swift hover:bg-ink",
                n === state.beat ? "bg-electric" : n < state.beat ? "bg-quiet" : "bg-line-strong",
              )}
            />
          ))}
        </div>

        <div className="mx-1 h-4 w-px bg-line" />

        <HudButton title="Speed (dwell only)" onClick={() => engine.cycleSpeed()}>
          <span className="mono-label text-ink">{state.speed}×</span>
        </HudButton>

        <HudButton
          title={state.captionsOn ? "Captions off" : "Captions on"}
          onClick={() => engine.toggleCaptions()}
          active={state.captionsOn}
        >
          <span className="mono-label" style={{ color: "inherit" }}>
            cc
          </span>
        </HudButton>

        <div className="mx-1 h-4 w-px bg-line" />

        <span className="mono-label min-w-[104px] whitespace-nowrap px-1 text-left">
          b{String(state.beat).padStart(2, "0")}/{BEAT_COUNT} ·{" "}
          {STATUS_LABEL[state.status] ?? state.status}
          {state.status === "stalled" && " — → skips"}
        </span>
      </div>
    </div>
  );
}
