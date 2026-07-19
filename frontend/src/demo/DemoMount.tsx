/**
 * Track E, demo activation. Mounted once inside BrowserRouter (App.tsx).
 *
 * URL contract (read once, at mount):
 *   ?demo=1              → engine armed (data factory already forced mock mode)
 *   ?demo=1&autopilot=1  → HUD mounted and ready (paused; Space starts)
 *   ?demo=1&beat=N       → applyScenario(checkpoint at-or-before N) + navigate
 *                          to beat N's entry route, paused there
 *
 * Renders null when ?demo is absent. Ctrl+. toggles the HUD even when armed
 * without autopilot; Shift+R is the full reset.
 */
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getDemoEngine, useEngineState } from "@/demo/engine";
import { ActInterstitial } from "@/demo/ActInterstitial";
import { DemoHud } from "@/demo/DemoHud";
import { DemoSpotlight } from "@/demo/spotlight";
import { BEAT_COUNT } from "@/demo/script";

function parseBeat(raw: string | null): number | undefined {
  if (!raw) return undefined;
  const n = Number.parseInt(raw, 10);
  if (!Number.isFinite(n) || n < 1 || n > BEAT_COUNT) return undefined;
  return n;
}

export function DemoMount() {
  // Read activation exactly once, engine navigations must not re-trigger it.
  const [boot] = useState(() => {
    const params = new URLSearchParams(window.location.search);
    return {
      armed: params.get("demo") === "1",
      autopilot: params.get("autopilot") === "1",
      beat: parseBeat(params.get("beat")),
    };
  });
  const navigate = useNavigate();
  const engine = useMemo(() => (boot.armed ? getDemoEngine() : null), [boot.armed]);

  // Keep the engine's navigate fresh (react-router recreates it per location).
  useEffect(() => {
    engine?.setNavigate(navigate);
  }, [engine, navigate]);

  useEffect(() => {
    if (!engine) return;
    engine.arm({ autopilot: boot.autopilot, beat: boot.beat });
    return () => engine.disarm();
    // boot is stable by construction (useState initializer).
  }, [engine, boot]);

  if (!engine) return null;

  return (
    <>
      <DemoSpotlight engine={engine} />
      <InterstitialLayer engine={engine} />
      <DemoHud engine={engine} />
    </>
  );
}

function InterstitialLayer({ engine }: { engine: ReturnType<typeof getDemoEngine> }) {
  const state = useEngineState(engine);
  return <ActInterstitial interstitial={state.interstitial} />;
}
