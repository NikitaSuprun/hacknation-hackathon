/**
 * CSS-only layered-gradient "paint poster" backdrop for the public pages
 * (landing + /chosen). Three big pre-blurred gradient layers — electric,
 * cream, low-opacity ink — with the blur set once on the wrapper and never
 * animated. The single ambient motion is one slow 60s transform rotation.
 * A cream veil keeps foreground text readable; the global reduced-motion
 * clamp in index.css stops the rotation. No WebGL, no canvas, no JS.
 *
 * `subtle` dials the layers down for the landing hero, where the wordmark
 * carries the page and the poster should only hum in the background.
 * `mono` drops the electric entirely — used on /chosen, where nobody has
 * been chosen yet and the accent would be a false promise.
 */
export function PosterBackdrop({
  subtle = false,
  mono = false,
}: {
  subtle?: boolean;
  mono?: boolean;
}) {
  const warm = mono ? "rgba(111, 111, 99, " : "rgba(0, 55, 255, ";
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
      <style>{`
        @keyframes chosen-radar-spin {
          from { transform: translate(-50%, -50%) rotate(0deg); }
          to { transform: translate(-50%, -50%) rotate(360deg); }
        }
      `}</style>
      <div
        className="absolute left-1/2 top-1/2 h-[160vmax] w-[160vmax]"
        style={{
          transform: "translate(-50%, -50%)",
          filter: "blur(90px)",
          animation: "chosen-radar-spin 60s linear infinite",
          willChange: "transform",
          opacity: subtle ? 0.55 : 1,
        }}
      >
        <div
          className="absolute inset-0"
          style={{
            background: `radial-gradient(closest-side at 31% 34%, ${warm}${mono ? 0.4 : 0.46}), ${warm}0) 62%)`,
          }}
        />
        <div
          className="absolute inset-0"
          style={{
            background: `radial-gradient(closest-side at 68% 64%, ${warm}0.24), ${warm}0) 55%)`,
          }}
        />
        <div
          className="absolute inset-0"
          style={{
            background: `conic-gradient(from 60deg at 52% 48%, rgba(250, 247, 234, 0) 0deg, rgba(14, 14, 12, 0.09) 110deg, rgba(250, 247, 234, 0) 200deg, ${warm}0.14) 290deg, rgba(250, 247, 234, 0) 360deg)`,
          }}
        />
      </div>
      {/* Cream veil — ~70% paper so text on the poster stays readable. */}
      <div
        className="absolute inset-0"
        style={{ background: subtle ? "rgba(250, 247, 234, 0.8)" : "rgba(250, 247, 234, 0.7)" }}
      />
    </div>
  );
}
