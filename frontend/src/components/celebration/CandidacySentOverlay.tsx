import { useEffect, useRef, useState, type CSSProperties } from "react";
import { onCelebrate, type CandidacySentEvent } from "@/lib/celebration";
import { cn } from "@/lib/utils";
import "./celebration.css";

/**
 * The brand's signature "candidacy sent" moment (~1600ms, CSS only).
 * Mounted once at the app root; plays whenever lib/celebration fires -
 * the real send action and the demo engine share this one code path.
 *
 * Timeline (normal):
 *   0-120ms    circular clip-path reveal of the paint burst from event.origin
 *   300-900ms  center card rises
 *   1100ms     fade-out begins (320ms ease-travel)
 *   1600ms     unmount, body scroll restored
 * Skippable: any pointerdown/keydown jumps straight to the fade-out.
 * Reduced motion: no burst, 150ms card crossfade, auto-dismiss at 900ms.
 */
interface PlayState {
  event: CandidacySentEvent;
  playId: number;
  reduced: boolean;
}

export function CandidacySentOverlay() {
  const [play, setPlay] = useState<PlayState | null>(null);
  const [exiting, setExiting] = useState(false);
  const exitingRef = useRef(false);
  const timersRef = useRef<number[]>([]);

  const clearTimers = () => {
    for (const id of timersRef.current) window.clearTimeout(id);
    timersRef.current = [];
  };

  useEffect(() => {
    return onCelebrate((event) => {
      clearTimers();
      exitingRef.current = false;
      setExiting(false);
      setPlay({
        event,
        playId: Date.now(),
        reduced: window.matchMedia("(prefers-reduced-motion: reduce)").matches,
      });
    });
  }, []);

  useEffect(() => {
    if (!play) return;

    const dismiss = () => {
      clearTimers();
      exitingRef.current = false;
      setExiting(false);
      setPlay(null);
    };
    const startExit = () => {
      exitingRef.current = true;
      setExiting(true);
    };
    // Skip: jump straight to the fade-out (single class toggle).
    const skip = () => {
      if (exitingRef.current) return;
      clearTimers();
      startExit();
      timersRef.current.push(window.setTimeout(dismiss, play.reduced ? 170 : 340));
    };

    timersRef.current.push(window.setTimeout(startExit, play.reduced ? 720 : 1100));
    timersRef.current.push(window.setTimeout(dismiss, play.reduced ? 900 : 1600));
    window.addEventListener("pointerdown", skip);
    window.addEventListener("keydown", skip);

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    return () => {
      clearTimers();
      window.removeEventListener("pointerdown", skip);
      window.removeEventListener("keydown", skip);
      document.body.style.overflow = previousOverflow;
    };
  }, [play]);

  if (!play) return null;
  const { event, playId, reduced } = play;

  const originStyle = event.origin
    ? ({ "--burst-x": `${event.origin.x}px`, "--burst-y": `${event.origin.y}px` } as CSSProperties)
    : undefined;

  return (
    <div key={playId} className={cn("celebration-overlay", exiting && "is-exiting")}>
      <div role="status" aria-live="polite" className="sr-only">
        Invitation sent. {event.ventureName} chosen.
      </div>

      {!reduced && (
        <div className="celebration-burst" style={originStyle} aria-hidden>
          <div className="celebration-burst__layer celebration-burst__layer--electric" />
          <div className="celebration-burst__layer celebration-burst__layer--cream" />
          <div className="celebration-burst__layer celebration-burst__layer--ink" />
        </div>
      )}

      <div className={cn("celebration-card", reduced && "celebration-card--reduced")}>
        <div className="border border-line bg-paper px-10 py-8 text-center shadow-lift">
          <p className="mono-label text-electric">Invitation sent</p>
          <p className="mt-2 font-display text-h2 text-ink">{event.ventureName}, chosen.</p>
          {event.founderName && (
            <p className="mt-1 text-small text-quiet">
              Interview invitation sent to {event.founderName}.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
