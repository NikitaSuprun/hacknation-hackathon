import { useEffect, useRef } from "react";

/**
 * The founder-side hero background: a CSS-only layered-gradient "paint
 * poster". Three large gradient layers (electric, cream, ink at low opacity)
 * are blurred once on their wrapper, never animated, behind a cream veil
 * so the headline stays AAA-readable. The one ambient motion is a very slow
 * 60s rotation of the layer wrapper (transform only), paused while the
 * document is hidden; the global reduced-motion clamp handles the rest.
 */
export function PaintPoster() {
  const layersRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = layersRef.current;
    if (!el) return;
    const onVisibility = () => {
      el.style.animationPlayState = document.hidden ? "paused" : "running";
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, []);

  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
      <style>{`
        @keyframes chosen-poster-spin {
          from { transform: translate(-50%, -50%) rotate(0deg); }
          to { transform: translate(-50%, -50%) rotate(360deg); }
        }
      `}</style>
      <div
        ref={layersRef}
        className="absolute left-1/2 top-1/2 h-[165vmax] w-[165vmax]"
        style={{
          filter: "blur(80px)",
          animation: "chosen-poster-spin 60s linear infinite",
          willChange: "transform",
        }}
      >
        <div
          className="absolute inset-0"
          style={{
            background:
              "radial-gradient(closest-side at 33% 36%, rgba(0, 55, 255, 0.5), rgba(0, 55, 255, 0) 62%)",
          }}
        />
        <div
          className="absolute inset-0"
          style={{
            background:
              "radial-gradient(closest-side at 67% 62%, rgba(0, 55, 255, 0.26), rgba(0, 55, 255, 0) 55%)",
          }}
        />
        <div
          className="absolute inset-0"
          style={{
            background:
              "conic-gradient(from 40deg at 55% 45%, rgba(250, 247, 234, 0) 0deg, rgba(14, 14, 12, 0.1) 120deg, rgba(250, 247, 234, 0) 220deg, rgba(0, 55, 255, 0.16) 300deg, rgba(250, 247, 234, 0) 360deg)",
          }}
        />
      </div>
      {/* Cream veil, keeps text on the poster AAA-readable. */}
      <div className="absolute inset-0" style={{ background: "rgba(250, 247, 234, 0.72)" }} />
    </div>
  );
}
