/**
 * Stage 3 of thesis intake — the structured form over gold.thesis.
 * Two entries: fresh from extraction (missing fields blank + red, extracted
 * fields tagged) or from the confirmed card (prefilled = true: everything
 * filled, no danger treatment — a plain edit form). Live mode always uses
 * the prefilled variant.
 */
import { useState, type ReactNode } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { dataSource } from "@/lib/data";
import type { Thesis, ThesisInput } from "@/lib/domain/types";
import { cn } from "@/lib/utils";
import {
  countWord,
  missingThingCount,
  toForm,
  toInput,
  toIntakeForm,
  type ThesisForm,
} from "@/components/thesis/thesisForm";

type FieldTag = "extracted" | "missing" | null;

function TagBadge({ tag }: { tag: FieldTag }) {
  if (tag === "extracted")
    return <span className="font-mono text-mono-label text-quiet">extracted</span>;
  if (tag === "missing")
    return <span className="font-mono text-mono-label text-danger">needs input</span>;
  return null;
}

function FieldLabel({
  htmlFor,
  tag,
  children,
}: {
  htmlFor: string;
  tag: FieldTag;
  children: ReactNode;
}) {
  return (
    <div className="flex items-baseline justify-between">
      <Label htmlFor={htmlFor} className="mono-label">
        {children}
      </Label>
      <TagBadge tag={tag} />
    </div>
  );
}

export function ReviewStage({
  thesis,
  missingFields,
  prefilled,
  onConfirmed,
  onCancel,
  onStartOver,
}: {
  thesis: Thesis;
  missingFields: string[];
  /** True when reached from the confirmed card (or in live mode): all fields prefill, no danger treatment. */
  prefilled: boolean;
  onConfirmed: () => void;
  /** Prefilled edit only — return to the confirmed card without saving. */
  onCancel: () => void;
  /** Fresh intake only — throw the extraction away and start again. */
  onStartOver: (() => void) | null;
}) {
  const ds = dataSource();
  const queryClient = useQueryClient();
  const [form, setForm] = useState<ThesisForm>(() =>
    prefilled ? toForm(thesis) : toIntakeForm(thesis, missingFields),
  );

  const save = useMutation({
    mutationFn: (input: ThesisInput) => ds.saveThesis(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["theses"] });
      toast("Thesis confirmed.");
      onConfirmed();
    },
    onError: (err) =>
      toast.error(`Save failed${err instanceof Error ? `: ${err.message}` : ""}.`),
  });

  const set = <K extends keyof ThesisForm>(key: K, value: ThesisForm[K]) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  const missing = new Set(prefilled ? [] : missingFields);
  const checkMinMissing = missing.has("check_size_min_chf");
  const checkMaxMissing = missing.has("check_size_max_chf");
  const policiesMissing =
    missing.has("require_no_prior_vc") || missing.has("exclude_corporate_oss");

  // Extracted tag only in the intake narrative; a prefilled edit is a plain form.
  const tagOf = (field: string): FieldTag =>
    prefilled ? null : missing.has(field) ? "missing" : "extracted";

  const incomplete =
    (checkMinMissing && form.checkMin.trim() === "") ||
    (checkMaxMissing && form.checkMax.trim() === "");

  const thingCount = missingThingCount(missingFields);

  return (
    <div className="animate-fade-up">
      <p className="mono-label mb-2">Investment thesis</p>
      {prefilled ? (
        <>
          <h1 className="font-display text-h1">Update thesis.</h1>
          <p className="mt-3 text-body text-quiet">Adjust any field and confirm.</p>
        </>
      ) : (
        <>
          <h1 className="font-display text-h1">Almost there.</h1>
          <p className="mt-3 max-w-measure text-body text-quiet">
            {thingCount > 0
              ? `${countWord(thingCount)} ${thingCount === 1 ? "thing" : "things"} we could not read. The red fields need the committee.`
              : "Here is what we read. Confirm to continue."}
          </p>
        </>
      )}

      <form
        className="mt-10 max-w-2xl"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate(toInput(thesis, form));
        }}
      >
        <div className="space-y-6">
          <div>
            <FieldLabel htmlFor="thesis-name" tag={tagOf("name")}>
              Name
            </FieldLabel>
            <Input
              id="thesis-name"
              className="mt-1.5"
              value={form.name}
              onChange={(e) => set("name", e.target.value)}
            />
          </div>

          <div className="grid gap-6 sm:grid-cols-3">
            <div>
              <FieldLabel htmlFor="thesis-sectors" tag={tagOf("sectors")}>
                Sectors
              </FieldLabel>
              <Input
                id="thesis-sectors"
                className="mt-1.5"
                value={form.sectors}
                onChange={(e) => set("sectors", e.target.value)}
                placeholder="robotics, ai"
              />
            </div>
            <div>
              <FieldLabel htmlFor="thesis-geographies" tag={tagOf("geographies")}>
                Geographies
              </FieldLabel>
              <Input
                id="thesis-geographies"
                className="mt-1.5"
                value={form.geographies}
                onChange={(e) => set("geographies", e.target.value)}
                placeholder="CH, EU"
              />
            </div>
            <div>
              <FieldLabel htmlFor="thesis-stages" tag={tagOf("stages")}>
                Stages
              </FieldLabel>
              <Input
                id="thesis-stages"
                className="mt-1.5"
                value={form.stages}
                onChange={(e) => set("stages", e.target.value)}
                placeholder="pre-seed, seed"
              />
            </div>
          </div>
          <p className="-mt-4 font-mono text-[11px] text-quiet">comma-separated</p>

          <div className="grid gap-6 sm:grid-cols-2">
            <div>
              <FieldLabel htmlFor="thesis-check-min" tag={tagOf("check_size_min_chf")}>
                Check size min · CHF
              </FieldLabel>
              <Input
                id="thesis-check-min"
                data-demo-id="thesis-field-check-min"
                type="number"
                min={0}
                step={50000}
                className={cn(
                  "mt-1.5 font-mono text-mono-data tabular",
                  checkMinMissing && "border-danger",
                )}
                value={form.checkMin}
                onChange={(e) => set("checkMin", e.target.value)}
              />
            </div>
            <div>
              <FieldLabel htmlFor="thesis-check-max" tag={tagOf("check_size_max_chf")}>
                Check size max · CHF
              </FieldLabel>
              <Input
                id="thesis-check-max"
                data-demo-id="thesis-field-check-max"
                type="number"
                min={0}
                step={50000}
                className={cn(
                  "mt-1.5 font-mono text-mono-data tabular",
                  checkMaxMissing && "border-danger",
                )}
                value={form.checkMax}
                onChange={(e) => set("checkMax", e.target.value)}
              />
            </div>
          </div>

          <div className="grid gap-6 sm:grid-cols-2">
            <div>
              <FieldLabel htmlFor="thesis-min-team" tag={tagOf("min_team")}>
                Min team
              </FieldLabel>
              <Input
                id="thesis-min-team"
                type="number"
                min={1}
                className="mt-1.5 font-mono text-mono-data tabular"
                value={form.minTeam}
                onChange={(e) => set("minTeam", e.target.value)}
              />
            </div>
            <div>
              <FieldLabel htmlFor="thesis-max-team" tag={tagOf("max_team")}>
                Max team
              </FieldLabel>
              <Input
                id="thesis-max-team"
                type="number"
                min={1}
                className="mt-1.5 font-mono text-mono-data tabular"
                value={form.maxTeam}
                onChange={(e) => set("maxTeam", e.target.value)}
              />
            </div>
          </div>

          <div className="hairline-t hairline-b space-y-4 py-5">
            {policiesMissing && (
              <div className="flex items-baseline justify-between">
                <span className="mono-label">Policies</span>
                <TagBadge tag="missing" />
              </div>
            )}
            <label className="flex cursor-pointer items-start gap-3">
              <Checkbox
                data-demo-id="thesis-field-no-prior-vc"
                checked={form.requireNoPriorVc}
                onCheckedChange={(checked) => set("requireNoPriorVc", checked === true)}
                className={cn("mt-0.5", missing.has("require_no_prior_vc") && "border-danger")}
              />
              <span>
                <span className="block text-small font-medium text-ink">
                  Require no prior VC
                </span>
                <span className="block text-small text-quiet">
                  Only ventures with no institutional funding signal enter the pool.
                </span>
              </span>
            </label>
            <label className="flex cursor-pointer items-start gap-3">
              <Checkbox
                data-demo-id="thesis-field-corporate-oss"
                checked={form.excludeCorporateOss}
                onCheckedChange={(checked) => set("excludeCorporateOss", checked === true)}
                className={cn("mt-0.5", missing.has("exclude_corporate_oss") && "border-danger")}
              />
              <span>
                <span className="block text-small font-medium text-ink">
                  Exclude corporate OSS
                </span>
                <span className="block text-small text-quiet">
                  Drop repositories maintained by established companies.
                </span>
              </span>
            </label>
          </div>

          <div>
            <FieldLabel htmlFor="thesis-notes" tag={tagOf("notes")}>
              Notes
            </FieldLabel>
            <Textarea
              id="thesis-notes"
              className="mt-1.5"
              value={form.notes}
              onChange={(e) => set("notes", e.target.value)}
              placeholder="What this thesis is really hunting for."
            />
          </div>
        </div>

        <div className="mt-8 flex items-center justify-between gap-4">
          {prefilled ? (
            <button
              type="button"
              onClick={onCancel}
              className="text-small text-quiet underline underline-offset-4 transition-colors duration-120 ease-swift hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              Cancel
            </button>
          ) : onStartOver ? (
            <button
              type="button"
              data-demo-id="btn-thesis-start-over"
              onClick={onStartOver}
              className="text-small text-quiet underline underline-offset-4 transition-colors duration-120 ease-swift hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              Start over
            </button>
          ) : (
            <span />
          )}
          <Button type="submit" data-demo-id="btn-thesis-save" disabled={save.isPending || incomplete}>
            {save.isPending ? "Saving…" : "Confirm thesis"}
          </Button>
        </div>
      </form>
    </div>
  );
}
