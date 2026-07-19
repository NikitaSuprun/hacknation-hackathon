import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { useIdealCandidate } from "@/hooks/useInvestorData";
import { dataSource } from "@/lib/data";
import type { IdealCandidateProfile } from "@/lib/domain/types";

interface EducationRow {
  institution: string;
  level: string;
  field: string;
}

interface FeatureRow {
  key: string;
  value: string;
  weight: string;
}

interface IdealForm {
  narrative: string;
  education: EducationRow[];
  sectors: string;
  keywords: string;
  features: FeatureRow[];
}

function toForm(profile: IdealCandidateProfile): IdealForm {
  const keys = new Set([
    ...Object.keys(profile.numeric_features ?? {}),
    ...Object.keys(profile.feature_weights ?? {}),
  ]);
  return {
    narrative: profile.narrative ?? "",
    education: (profile.education ?? []).map((e) => ({
      institution: e.institution,
      level: e.level ?? "",
      field: e.field ?? "",
    })),
    sectors: (profile.sectors ?? []).join(", "),
    keywords: (profile.keywords ?? []).join(", "),
    features: [...keys].map((key) => ({
      key,
      value: profile.numeric_features?.[key] != null ? String(profile.numeric_features[key]) : "",
      weight: profile.feature_weights?.[key] != null ? String(profile.feature_weights![key]) : "",
    })),
  };
}

function parseList(value: string): string[] {
  return value
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

function toProfile(base: IdealCandidateProfile, form: IdealForm): IdealCandidateProfile {
  const numeric_features: Record<string, number> = {};
  const feature_weights: Record<string, number> = {};
  for (const row of form.features) {
    const key = row.key.trim();
    if (!key) continue;
    if (row.value.trim() !== "" && !Number.isNaN(Number(row.value))) {
      numeric_features[key] = Number(row.value);
    }
    if (row.weight.trim() !== "" && !Number.isNaN(Number(row.weight))) {
      feature_weights[key] = Number(row.weight);
    }
  }
  return {
    schema_version: base.schema_version ?? 1,
    narrative: form.narrative.trim() || null,
    education: form.education
      .filter((e) => e.institution.trim() !== "")
      .map((e) => ({
        institution: e.institution.trim(),
        level: e.level.trim() || null,
        field: e.field.trim() || null,
      })),
    sectors: parseList(form.sectors),
    keywords: parseList(form.keywords),
    numeric_features,
    feature_weights,
  };
}

/** Structured editor over gold.ideal_candidate.profile_json — saving queues a re-embed. */
export default function IdealEditorPage() {
  const { thesisId = "" } = useParams();
  const ds = dataSource();
  const queryClient = useQueryClient();
  const { data: profile, isLoading, isError, error, refetch } = useIdealCandidate(thesisId);
  const [form, setForm] = useState<IdealForm | null>(null);

  useEffect(() => {
    if (profile && form === null) setForm(toForm(profile));
  }, [profile, form]);

  const save = useMutation({
    mutationFn: (next: IdealCandidateProfile) => ds.saveIdealCandidate(thesisId, next),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["ideal", thesisId] });
      toast("Saved — re-embedding queued.");
    },
    onError: (err) =>
      toast.error(`Save failed${err instanceof Error ? ` — ${err.message}` : ""}.`),
  });

  const set = <K extends keyof IdealForm>(key: K, value: IdealForm[K]) =>
    setForm((prev) => (prev ? { ...prev, [key]: value } : prev));

  const setEducation = (index: number, patch: Partial<EducationRow>) =>
    setForm((prev) =>
      prev
        ? {
            ...prev,
            education: prev.education.map((row, i) =>
              i === index ? { ...row, ...patch } : row,
            ),
          }
        : prev,
    );

  const setFeature = (index: number, patch: Partial<FeatureRow>) =>
    setForm((prev) =>
      prev
        ? {
            ...prev,
            features: prev.features.map((row, i) => (i === index ? { ...row, ...patch } : row)),
          }
        : prev,
    );

  if (isError) {
    return (
      <div className="max-w-measure-narrow py-gutter-lg">
        <p className="mono-label mb-2">Profile unavailable</p>
        <p className="text-body text-quiet">
          The ideal-candidate query failed{error instanceof Error ? ` — ${error.message}` : ""}.
        </p>
        <Button variant="outline" size="sm" className="mt-4" onClick={() => refetch()}>
          Retry
        </Button>
      </div>
    );
  }

  if (isLoading || !profile || !form) {
    return (
      <div className="py-gutter-lg">
        <Skeleton className="h-3 w-28" />
        <Skeleton className="mt-3 h-10 w-96 max-w-full" />
        <div className="mt-10 max-w-2xl space-y-6">
          {Array.from({ length: 5 }, (_, i) => (
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
      <p className="mono-label mb-2">Ideal candidate</p>
      <h1 className="font-display text-h1">Ideal-candidate profile</h1>
      <p className="mt-3 max-w-measure text-body text-quiet">
        The profile ventures are matched against — narrative for the embedding, features for the
        structured score.
      </p>

      <form
        className="mt-10 max-w-2xl"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate(toProfile(profile, form));
        }}
      >
        <div className="space-y-8">
          <div>
            <Label htmlFor="ideal-narrative" className="mono-label">
              Narrative
            </Label>
            <Textarea
              id="ideal-narrative"
              className="mt-1.5"
              value={form.narrative}
              onChange={(e) => set("narrative", e.target.value)}
              placeholder="Who gets chosen, in one paragraph."
            />
          </div>

          <div>
            <p className="mono-label">Education</p>
            <div className="mt-1.5 space-y-2">
              {form.education.map((row, i) => (
                <div key={i} className="grid grid-cols-[1fr_7rem_1fr_auto] items-center gap-2">
                  <Input
                    value={row.institution}
                    onChange={(e) => setEducation(i, { institution: e.target.value })}
                    placeholder="Institution"
                    aria-label="Institution"
                  />
                  <Input
                    value={row.level}
                    onChange={(e) => setEducation(i, { level: e.target.value })}
                    placeholder="Level"
                    aria-label="Level"
                  />
                  <Input
                    value={row.field}
                    onChange={(e) => setEducation(i, { field: e.target.value })}
                    placeholder="Field"
                    aria-label="Field"
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() =>
                      set(
                        "education",
                        form.education.filter((_, j) => j !== i),
                      )
                    }
                  >
                    Remove
                  </Button>
                </div>
              ))}
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() =>
                  set("education", [...form.education, { institution: "", level: "", field: "" }])
                }
              >
                + Add education
              </Button>
            </div>
          </div>

          <div className="grid gap-6 sm:grid-cols-2">
            <div>
              <Label htmlFor="ideal-sectors" className="mono-label">
                Sectors
              </Label>
              <Input
                id="ideal-sectors"
                className="mt-1.5"
                value={form.sectors}
                onChange={(e) => set("sectors", e.target.value)}
                placeholder="robotics"
              />
            </div>
            <div>
              <Label htmlFor="ideal-keywords" className="mono-label">
                Keywords
              </Label>
              <Input
                id="ideal-keywords"
                className="mt-1.5"
                value={form.keywords}
                onChange={(e) => set("keywords", e.target.value)}
                placeholder="manipulation, grasping"
              />
            </div>
          </div>
          <p className="-mt-6 font-mono text-[11px] text-quiet">comma-separated</p>

          <div>
            <p className="mono-label">Numeric features · weights</p>
            <div className="mt-1.5">
              <div className="hairline-b grid grid-cols-[minmax(0,1fr)_6.5rem_6.5rem_auto] gap-2 pb-1.5">
                <span className="font-mono text-[11px] uppercase tracking-[0.06em] text-quiet">
                  key
                </span>
                <span className="font-mono text-[11px] uppercase tracking-[0.06em] text-quiet">
                  value
                </span>
                <span className="font-mono text-[11px] uppercase tracking-[0.06em] text-quiet">
                  weight
                </span>
                <span />
              </div>
              <div className="mt-2 space-y-2">
                {form.features.map((row, i) => (
                  <div
                    key={i}
                    className="grid grid-cols-[minmax(0,1fr)_6.5rem_6.5rem_auto] items-center gap-2"
                  >
                    <Input
                      className="font-mono text-mono-data"
                      value={row.key}
                      onChange={(e) => setFeature(i, { key: e.target.value })}
                      placeholder="feature_key"
                      aria-label="Feature key"
                    />
                    <Input
                      type="number"
                      step="0.05"
                      className="font-mono text-mono-data tabular"
                      value={row.value}
                      onChange={(e) => setFeature(i, { value: e.target.value })}
                      aria-label="Feature value"
                    />
                    <Input
                      type="number"
                      step="0.05"
                      className="font-mono text-mono-data tabular"
                      value={row.weight}
                      onChange={(e) => setFeature(i, { weight: e.target.value })}
                      aria-label="Feature weight"
                    />
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() =>
                        set(
                          "features",
                          form.features.filter((_, j) => j !== i),
                        )
                      }
                    >
                      Remove
                    </Button>
                  </div>
                ))}
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() =>
                    set("features", [...form.features, { key: "", value: "", weight: "" }])
                  }
                >
                  + Add feature
                </Button>
              </div>
            </div>
          </div>
        </div>

        <div className="mt-8 flex justify-end">
          <Button type="submit" disabled={save.isPending}>
            {save.isPending ? "Saving…" : "Save profile"}
          </Button>
        </div>
      </form>
    </div>
  );
}
