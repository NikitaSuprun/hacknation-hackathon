import { useEffect, useState } from "react";
import { onCelebrate, type CandidacySentEvent } from "@/lib/celebration";

/**
 * The signature "candidacy sent" moment. Mounted once at the app root;
 * plays whenever lib/celebration fires (real send or demo engine).
 *
 * TODO(Track D): full 1600ms storyboard — button compress → card lift →
 * CSS paint burst from origin → chip flip → kanban slide. Skippable on any
 * pointer/key event; reduced-motion = 150ms crossfade.
 */
export function CandidacySentOverlay() {
  const [event, setEvent] = useState<CandidacySentEvent | null>(null);

  useEffect(() => {
    return onCelebrate((e) => {
      setEvent(e);
      window.setTimeout(() => setEvent(null), 1600);
    });
  }, []);

  if (!event) return null;

  return (
    <div
      className="pointer-events-none fixed inset-0 z-[60] flex items-center justify-center animate-fade-in"
      aria-live="polite"
    >
      <div className="border border-electric bg-paper px-8 py-6 shadow-lift">
        <p className="mono-label mb-1 text-electric">Candidacy sent</p>
        <p className="font-display text-h2 text-ink">{event.ventureName} — chosen.</p>
      </div>
    </div>
  );
}
