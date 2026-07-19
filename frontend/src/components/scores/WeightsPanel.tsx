import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { X } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Slider } from "@/components/ui/slider";
import { useWeights } from "@/hooks/useInvestorData";
import { dataSource } from "@/lib/data";
import {
  CATEGORY_KEYS,
  CATEGORY_LABELS,
  type CategoryKey,
  type ScoreWeights,
  weightKey,
} from "@/lib/domain/types";
import { cn } from "@/lib/utils";

export interface WeightsPanelProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  thesisId: string;
  /**
   * Live-preview seam: called with the in-progress weights on every slider
   * change, and with null on reset, close, and after a save has settled
   * (invalidation refetched) so the server ranking takes over seamlessly.
   */
  onPreviewWeights?: (w: ScoreWeights | null) => void;
}

/**
 * The 9-slider weights editor as an on-demand right-side sheet. The ranked
 * list behind it is the live preview: every slider change pushes the local
 * weights up via onPreviewWeights so the page re-ranks its pool client-side.
 * Releasing a slider saves through the seam.
 */
export function WeightsPanel({ open, onOpenChange, thesisId, onPreviewWeights }: WeightsPanelProps) {
  const ds = dataSource();
  const queryClient = useQueryClient();
  const weightsQuery = useWeights(thesisId);

  const [local, setLocal] = useState<ScoreWeights | null>(null);
  const weights = local ?? weightsQuery.data ?? null;
  const latestRef = useRef<ScoreWeights | null>(null);

  const [flashKey, setFlashKey] = useState<CategoryKey | null>(null);
  const flashTimer = useRef<number | undefined>(undefined);

  // Keep callback refs fresh so the effects below never re-subscribe on
  // parent re-renders.
  const onPreviewRef = useRef(onPreviewWeights);
  onPreviewRef.current = onPreviewWeights;
  const onOpenChangeRef = useRef(onOpenChange);
  onOpenChangeRef.current = onOpenChange;

  // Slide-in: mount translated off-screen, flip to translate-x-0 a frame
  // later so the transform transition runs. The global reduced-motion clamp
  // shrinks the duration automatically.
  const [entered, setEntered] = useState(false);
  useEffect(() => {
    if (!open) {
      setEntered(false);
      return;
    }
    let raf2 = 0;
    const raf1 = requestAnimationFrame(() => {
      raf2 = requestAnimationFrame(() => setEntered(true));
    });
    return () => {
      cancelAnimationFrame(raf1);
      cancelAnimationFrame(raf2);
    };
  }, [open]);

  // Escape closes. No focus trap: the list behind stays interactive.
  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onOpenChangeRef.current(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open]);

  // Closing always hands the ranking back to the saved weights.
  useEffect(() => {
    if (!open) onPreviewRef.current?.(null);
  }, [open]);

  useEffect(() => () => window.clearTimeout(flashTimer.current), []);

  const totalWeight = useMemo(() => {
    if (!weights) return 0;
    return CATEGORY_KEYS.reduce((sum, key) => sum + (weights[weightKey(key)] as number), 0);
  }, [weights]);

  const save = useMutation({
    mutationFn: (w: ScoreWeights) => ds.saveWeights(thesisId, w),
    onSuccess: async (_data, saved) => {
      toast("Weights saved. Ranking updated.");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["weights"] }),
        queryClient.invalidateQueries({ queryKey: ["ranking"] }),
      ]);
      // Only drop the preview if no newer drag superseded this save — the
      // refetched ranking now carries the same order, so the handoff is
      // seamless.
      if (latestRef.current === saved) onPreviewRef.current?.(null);
    },
    onError: (error) =>
      toast.error(`Save failed${error instanceof Error ? `: ${error.message}` : ""}.`),
  });

  const onChange = (key: CategoryKey, value: number) => {
    const base = local ?? weightsQuery.data;
    if (!base) return;
    const next = { ...base, [weightKey(key)]: value } as ScoreWeights;
    latestRef.current = next;
    setLocal(next);
    onPreviewWeights?.(next);
    setFlashKey(key);
    window.clearTimeout(flashTimer.current);
    flashTimer.current = window.setTimeout(() => setFlashKey(null), 240);
  };

  const onCommit = () => {
    const next = latestRef.current;
    if (next) save.mutate(next);
  };

  const reset = () => {
    setLocal(null);
    latestRef.current = null;
    onPreviewWeights?.(null);
  };

  const dirty =
    local != null &&
    weightsQuery.data != null &&
    CATEGORY_KEYS.some((key) => local[weightKey(key)] !== weightsQuery.data![weightKey(key)]);

  if (!open) return null;

  return (
    <aside
      data-demo-id="weights-panel"
      role="dialog"
      aria-label="Scoring weights"
      className={cn(
        "fixed inset-y-0 right-0 z-50 flex w-[380px] max-w-full flex-col border-l border-line bg-paper shadow-lift transition-transform duration-240 ease-travel",
        entered ? "translate-x-0" : "translate-x-full",
      )}
    >
      <div className="hairline-b flex items-start justify-between gap-4 py-4 pl-6 pr-3">
        <div>
          <p className="mono-label">Scoring weights</p>
          <p className="mt-1.5 text-small text-quiet">
            Defaults are sensible. Changes are saved when you release a slider.
          </p>
        </div>
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8 shrink-0"
          aria-label="Close weights panel"
          onClick={() => onOpenChange(false)}
        >
          <X strokeWidth={1.5} />
        </Button>
      </div>

      <div className="flex-1 overflow-y-auto px-6 py-2">
        {weightsQuery.isLoading &&
          Array.from({ length: 9 }, (_, i) => (
            <div key={i} className="py-4">
              <div className="flex justify-between">
                <Skeleton className="h-3 w-40" />
                <Skeleton className="h-3 w-10" />
              </div>
              <Skeleton className="mt-3 h-1 w-full" />
            </div>
          ))}

        {weightsQuery.isError && (
          <div className="py-6">
            <p className="mono-label mb-2">Weights unavailable</p>
            <p className="text-body text-quiet">
              The weights query failed
              {weightsQuery.error instanceof Error ? `: ${weightsQuery.error.message}` : ""}.
            </p>
            <Button
              variant="outline"
              size="sm"
              className="mt-4"
              onClick={() => weightsQuery.refetch()}
            >
              Retry
            </Button>
          </div>
        )}

        {!weightsQuery.isLoading &&
          weights &&
          CATEGORY_KEYS.map((key) => {
            const value = weights[weightKey(key)] as number;
            const share = totalWeight > 0 ? (value / totalWeight) * 100 : 0;
            return (
              <div key={key} className="hairline-b py-4 last:border-b-0">
                <div className="flex items-baseline justify-between gap-4">
                  <span className="mono-label">{CATEGORY_LABELS[key]}</span>
                  <span
                    className={cn(
                      "font-mono text-mono-data tabular transition-colors duration-240 ease-swift",
                      flashKey === key ? "text-electric" : "text-ink",
                    )}
                  >
                    {share.toFixed(1)}%
                  </span>
                </div>
                <Slider
                  data-demo-id={`slider-${key}`}
                  className="mt-1"
                  min={0}
                  max={0.3}
                  step={0.005}
                  value={[value]}
                  onValueChange={([v]) => onChange(key, v)}
                  onValueCommit={onCommit}
                  aria-label={CATEGORY_LABELS[key]}
                />
              </div>
            );
          })}
      </div>

      <div className="hairline-t flex items-center justify-between gap-3 px-6 py-3">
        <span className="font-mono text-[11px] text-quiet">
          {save.isPending ? "saving…" : "saves on release"}
        </span>
        <Button variant="ghost" size="sm" onClick={reset} disabled={!dirty}>
          Reset to saved
        </Button>
      </div>
    </aside>
  );
}
