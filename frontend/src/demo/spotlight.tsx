/**
 * Track E, the spotlight ring: a fixed, pointer-transparent electric outline
 * hugging the current target's bounding rect. Repositions via a rAF loop (so
 * scroll, resize, and layout shifts are all covered) and fades in/out on
 * opacity; the last box is kept during fade-out so the ring never snaps.
 */
import { useEffect, useRef, useState } from "react";
import { useEngineState, type DemoEngine } from "@/demo/engine";

interface Box {
  top: number;
  left: number;
  width: number;
  height: number;
}

const PAD = 8;

function sameBox(a: Box | null, b: Box): boolean {
  return (
    a !== null && a.top === b.top && a.left === b.left && a.width === b.width && a.height === b.height
  );
}

export function DemoSpotlight({ engine }: { engine: DemoEngine }) {
  const state = useEngineState(engine);
  const [box, setBox] = useState<Box | null>(null);
  const boxRef = useRef<Box | null>(null);

  useEffect(() => {
    if (!state.spotlight) return; // keep the last box so the fade-out stays put
    const selector = `[data-demo-id="${state.spotlight}"]`;
    let raf = 0;
    const measure = () => {
      const el = document.querySelector(selector);
      if (el) {
        const r = el.getBoundingClientRect();
        const next: Box = {
          top: Math.round(r.top),
          left: Math.round(r.left),
          width: Math.round(r.width),
          height: Math.round(r.height),
        };
        if (!sameBox(boxRef.current, next)) {
          boxRef.current = next;
          setBox(next);
        }
      }
      raf = requestAnimationFrame(measure);
    };
    raf = requestAnimationFrame(measure);
    return () => cancelAnimationFrame(raf);
  }, [state.spotlight]);

  const visible = state.spotlight !== null && box !== null;

  return (
    <div
      aria-hidden
      className="pointer-events-none fixed z-[90] rounded-ctrl border-2 border-electric transition-all duration-240 ease-swift"
      style={{
        top: (box?.top ?? 0) - PAD,
        left: (box?.left ?? 0) - PAD,
        width: (box?.width ?? 0) + PAD * 2,
        height: (box?.height ?? 0) + PAD * 2,
        opacity: visible ? 1 : 0,
        boxShadow: visible ? "0 0 0 4px var(--electric-wash)" : "none",
      }}
    />
  );
}
