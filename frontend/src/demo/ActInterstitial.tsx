/**
 * Centered act announcement: a near-opaque paper veil with the act tag,
 * a Clash Display title, and one quiet line of context. Self-timed fade
 * (in, hold, out) matched to the engine's INTERSTITIAL_MS; opacity only.
 */
export function ActInterstitial({
  interstitial,
}: {
  interstitial: { act: string; title: string; sub: string } | null;
}) {
  if (!interstitial) return null;
  return (
    <div
      aria-live="polite"
      className="pointer-events-none fixed inset-0 z-[110] flex items-center justify-center"
      style={{ animation: "demo-act-fade 2.8s ease-in-out both" }}
    >
      <style>{`
        @keyframes demo-act-fade {
          0% { opacity: 0; }
          12% { opacity: 1; }
          85% { opacity: 1; }
          100% { opacity: 0; }
        }
      `}</style>
      {/* Explicit rgba: Tailwind alpha modifiers can't compose over var() colors. */}
      <div className="absolute inset-0" style={{ background: "rgba(250, 247, 234, 0.96)" }} />
      <div className="relative px-gutter text-center">
        <p className="mono-label text-electric">{interstitial.act}</p>
        <p className="mt-4 font-display text-display text-ink">{interstitial.title}</p>
        <p className="mt-4 text-h3 font-normal text-quiet">{interstitial.sub}</p>
      </div>
    </div>
  );
}
