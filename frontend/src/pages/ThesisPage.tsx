import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { useTheses } from "@/hooks/useInvestorData";
import { dataSource } from "@/lib/data";
import type { Thesis, ThesisInput } from "@/lib/domain/types";

interface ThesisForm {
  name: string;
  sectors: string;
  geographies: string;
  stages: string;
  checkMin: string;
  checkMax: string;
  minTeam: string;
  maxTeam: string;
  requireNoPriorVc: boolean;
  excludeCorporateOss: boolean;
  notes: string;
}

function toForm(thesis: Thesis): ThesisForm {
  return {
    name: thesis.name,
    sectors: thesis.sectors.join(", "),
    geographies: thesis.geographies.join(", "),
    stages: thesis.stages.join(", "),
    checkMin: String(thesis.check_size_min_chf),
    checkMax: String(thesis.check_size_max_chf),
    minTeam: String(thesis.min_team),
    maxTeam: String(thesis.max_team),
    requireNoPriorVc: thesis.require_no_prior_vc,
    excludeCorporateOss: thesis.exclude_corporate_oss,
    notes: thesis.notes ?? "",
  };
}

function parseList(value: string): string[] {
  return value
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

function toInput(thesis: Thesis, form: ThesisForm): ThesisInput {
  return {
    thesis_id: thesis.thesis_id,
    name: form.name.trim() || thesis.name,
    owner_email: thesis.owner_email,
    sectors: parseList(form.sectors),
    geographies: parseList(form.geographies),
    stages: parseList(form.stages),
    check_size_min_chf: Number(form.checkMin) || 0,
    check_size_max_chf: Number(form.checkMax) || 0,
    min_team: Number(form.minTeam) || 0,
    max_team: Number(form.maxTeam) || 0,
    require_no_prior_vc: form.requireNoPriorVc,
    exclude_corporate_oss: form.excludeCorporateOss,
    notes: form.notes.trim() || null,
    is_active: thesis.is_active,
  };
}

/** Structured form over gold.thesis — the filter that builds the candidate pool. */
export default function ThesisPage() {
  const ds = dataSource();
  const queryClient = useQueryClient();
  const { data: theses, isLoading, isError, error, refetch } = useTheses();
  const thesis = theses?.[0];
  const [form, setForm] = useState<ThesisForm | null>(null);

  useEffect(() => {
    if (thesis && form === null) setForm(toForm(thesis));
  }, [thesis, form]);

  const save = useMutation({
    mutationFn: (input: ThesisInput) => ds.saveThesis(input),
    onSuccess: (saved) => {
      queryClient.invalidateQueries({ queryKey: ["theses"] });
      setForm(toForm(saved));
      toast("Thesis saved.");
    },
    onError: (err) =>
      toast.error(`Save failed${err instanceof Error ? ` — ${err.message}` : ""}.`),
  });

  const set = <K extends keyof ThesisForm>(key: K, value: ThesisForm[K]) =>
    setForm((prev) => (prev ? { ...prev, [key]: value } : prev));

  if (isError) {
    return (
      <div className="max-w-measure-narrow py-gutter-lg">
        <p className="mono-label mb-2">Thesis unavailable</p>
        <p className="text-body text-quiet">
          The thesis query failed{error instanceof Error ? ` — ${error.message}` : ""}.
        </p>
        <Button variant="outline" size="sm" className="mt-4" onClick={() => refetch()}>
          Retry
        </Button>
      </div>
    );
  }

  if (isLoading || !thesis || !form) {
    return (
      <div className="py-gutter-lg">
        <Skeleton className="h-3 w-16" />
        <Skeleton className="mt-3 h-10 w-80 max-w-full" />
        <div className="mt-10 max-w-2xl space-y-6">
          {Array.from({ length: 6 }, (_, i) => (
            <div key={i}>
              <Skeleton className="h-3 w-32" />
              <Skeleton className="mt-2 h-10 w-full" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="py-gutter-lg">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="mono-label mb-2">Thesis</p>
          <h1 className="font-display text-h1">{thesis.name}</h1>
        </div>
        <div className="text-right font-mono text-mono-data text-quiet">
          <p>{thesis.owner_email}</p>
          <p className="mt-0.5">updated {thesis.updated_at.slice(0, 10)}</p>
        </div>
      </div>

      <form
        className="mt-10 max-w-2xl"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate(toInput(thesis, form));
        }}
      >
        <div className="space-y-6">
          <div>
            <Label htmlFor="thesis-name" className="mono-label">
              Name
            </Label>
            <Input
              id="thesis-name"
              className="mt-1.5"
              value={form.name}
              onChange={(e) => set("name", e.target.value)}
            />
          </div>

          <div className="grid gap-6 sm:grid-cols-3">
            <div>
              <Label htmlFor="thesis-sectors" className="mono-label">
                Sectors
              </Label>
              <Input
                id="thesis-sectors"
                className="mt-1.5"
                value={form.sectors}
                onChange={(e) => set("sectors", e.target.value)}
                placeholder="robotics, ai"
              />
            </div>
            <div>
              <Label htmlFor="thesis-geographies" className="mono-label">
                Geographies
              </Label>
              <Input
                id="thesis-geographies"
                className="mt-1.5"
                value={form.geographies}
                onChange={(e) => set("geographies", e.target.value)}
                placeholder="CH, EU"
              />
            </div>
            <div>
              <Label htmlFor="thesis-stages" className="mono-label">
                Stages
              </Label>
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
              <Label htmlFor="thesis-check-min" className="mono-label">
                Check size min · CHF
              </Label>
              <Input
                id="thesis-check-min"
                type="number"
                min={0}
                step={50000}
                className="mt-1.5 font-mono text-mono-data tabular"
                value={form.checkMin}
                onChange={(e) => set("checkMin", e.target.value)}
              />
            </div>
            <div>
              <Label htmlFor="thesis-check-max" className="mono-label">
                Check size max · CHF
              </Label>
              <Input
                id="thesis-check-max"
                type="number"
                min={0}
                step={50000}
                className="mt-1.5 font-mono text-mono-data tabular"
                value={form.checkMax}
                onChange={(e) => set("checkMax", e.target.value)}
              />
            </div>
          </div>

          <div className="grid gap-6 sm:grid-cols-2">
            <div>
              <Label htmlFor="thesis-min-team" className="mono-label">
                Min team
              </Label>
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
              <Label htmlFor="thesis-max-team" className="mono-label">
                Max team
              </Label>
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
            <label className="flex cursor-pointer items-start gap-3">
              <Checkbox
                checked={form.requireNoPriorVc}
                onCheckedChange={(checked) => set("requireNoPriorVc", checked === true)}
                className="mt-0.5"
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
                checked={form.excludeCorporateOss}
                onCheckedChange={(checked) => set("excludeCorporateOss", checked === true)}
                className="mt-0.5"
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
            <Label htmlFor="thesis-notes" className="mono-label">
              Notes
            </Label>
            <Textarea
              id="thesis-notes"
              className="mt-1.5"
              value={form.notes}
              onChange={(e) => set("notes", e.target.value)}
              placeholder="What this thesis is really hunting for."
            />
          </div>
        </div>

        <div className="mt-8 flex justify-end">
          <Button type="submit" disabled={save.isPending}>
            {save.isPending ? "Saving…" : "Save thesis"}
          </Button>
        </div>
      </form>
    </div>
  );
}
