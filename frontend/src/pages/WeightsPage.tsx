import { useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Slider } from "@/components/ui/slider";
import { CompactRankRow } from "@/components/scores/CompactRankRow";
import {
  COLD_START_HINT,
  useColdStartHint,
  useFlashOnReorder,
  useRanking,
  useWeights,
} from "@/hooks/useInvestorData";
import { dataSource } from "@/lib/data";
import {
  CATEGORY_KEYS,
  CATEGORY_LABELS,
  type CategoryKey,
  type ScoreWeights,
  weightKey,
} from "@/lib/domain/types";
import { rerank } from "@/lib/ranking/rerank";
import { cn } from "@/lib/utils";

/**
 * The money move: 9 sliders, instant client-side re-rank in the live preview
 * (zero network — rerank() over the cached ranking), save on release.
 */
export default function WeightsPage() {
  const { thesisId = "" } = useParams();
  const ds = dataSource();
  const queryClient = useQueryClient();
  const weightsQuery = useWeights(thesisId);
  const rankingQuery = useRanking(thesisId);
  const loading = weightsQuery.isLoading || rankingQuery.isLoading;
  const coldStart = useColdStartHint(loading);

  const [local, setLocal] = useState<ScoreWeights | null>(null);
  const weights = local ?? weightsQuery.data ?? null;
  const latestRef = useRef<ScoreWeights | null>(null);

  const [flashKey, setFlashKey] = useState<CategoryKey | null>(null);
  const flashTimer = useRef<number | undefined>(undefined);

  const preview = useMemo(
    () => (weights && rankingQuery.data ? rerank(rankingQuery.data, weights) : null),
    [weights, rankingQuery.data],
  );
  const previewIds = useMemo(() => preview?.map((v) => v.venture_id), [preview]);
  const flashedRows = useFlashOnReorder(previewIds);

  const totalWeight = useMemo(() => {
    if (!weights) return 0;
    return CATEGORY_KEYS.reduce((sum, key) => sum + (weights[weightKey(key)] as number), 0);
  }, [weights]);

  const save = useMutation({
    mutationFn: (w: ScoreWeights) => ds.saveWeights(thesisId, w),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["weights"] });
      queryClient.invalidateQueries({ queryKey: ["ranking"] });
      toast("Weights saved — ranking updated.");
    },
    onError: (error) =>
      toast.error(`Save failed${error instanceof Error ? ` — ${error.message}` : ""}.`),
  });

  const onChange = (key: CategoryKey, value: number) => {
    setLocal((prev) => {
      const base = prev ?? weightsQuery.data;
      if (!base) return prev;
      const next = { ...base, [weightKey(key)]: value } as ScoreWeights;
      latestRef.current = next;
      return next;
    });
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
  };

  const dirty =
    local != null &&
    weightsQuery.data != null &&
    CATEGORY_KEYS.some((key) => local[weightKey(key)] !== weightsQuery.data![weightKey(key)]);

  return (
    <div className="py-gutter-lg">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="mono-label mb-2">Weights</p>
          <h1 className="font-display text-h1">Scoring weights</h1>
          <p className="mt-3 max-w-measure text-body text-quiet">
            Drag to reweight. The preview re-ranks instantly — releasing a slider saves and
            re-ranks the pool.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span className="font-mono text-[11px] text-quiet">
            {save.isPending ? "saving…" : "saves on release"}
          </span>
          <Button variant="ghost" size="sm" onClick={reset} disabled={!dirty}>
            Reset to saved
          </Button>
        </div>
      </div>

      {loading && (
        <div className="mt-10 grid gap-x-gutter-lg gap-y-gutter lg:grid-cols-[minmax(0,1fr)_18rem]">
          <div className="space-y-6">
            {Array.from({ length: 9 }, (_, i) => (
              <div key={i}>
                <div className="flex justify-between">
                  <Skeleton className="h-3 w-40" />
                  <Skeleton className="h-3 w-10" />
                </div>
                <Skeleton className="mt-3 h-1 w-full" />
              </div>
            ))}
          </div>
          <div className="space-y-2">
            {Array.from({ length: 8 }, (_, i) => (
              <Skeleton key={i} className="h-9 w-full" />
            ))}
          </div>
          {coldStart && (
            <p className="font-mono text-mono-data text-quiet lg:col-span-2">{COLD_START_HINT}</p>
          )}
        </div>
      )}

      {weightsQuery.isError && (
        <div className="max-w-measure-narrow py-gutter">
          <p className="mono-label mb-2">Weights unavailable</p>
          <p className="text-body text-quiet">
            The weights query failed
            {weightsQuery.error instanceof Error ? ` — ${weightsQuery.error.message}` : ""}.
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

      {!loading && weights && (
        <div className="mt-10 grid gap-x-gutter-lg gap-y-gutter lg:grid-cols-[minmax(0,1fr)_18rem]">
          <div>
            {CATEGORY_KEYS.map((key) => {
              const value = weights[weightKey(key)] as number;
              const share = totalWeight > 0 ? (value / totalWeight) * 100 : 0;
              return (
                <div key={key} className="hairline-b py-4 first:pt-0">
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

          <aside>
            <p className="mono-label">Live preview</p>
            <p className="mt-1 text-small text-quiet">
              Re-ranked locally as you drag — no network.
            </p>
            <div className="mt-4">
              {preview?.map((venture, index) => (
                <CompactRankRow
                  key={venture.venture_id}
                  rank={index + 1}
                  name={venture.name}
                  score={venture.final_score}
                  flash={flashedRows.has(venture.venture_id)}
                  muted={venture.quality_tier === "needs_more_data"}
                />
              ))}
            </div>
          </aside>
        </div>
      )}
    </div>
  );
}
