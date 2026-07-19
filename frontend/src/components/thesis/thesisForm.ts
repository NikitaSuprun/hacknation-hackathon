/**
 * Form model over gold.thesis shared by the review stage — string-typed
 * fields the inputs can hold, plus the mapping to/from the API shape.
 */
import type { Thesis, ThesisInput } from "@/lib/domain/types";

export interface ThesisForm {
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

export function toForm(thesis: Thesis): ThesisForm {
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

/**
 * Initial review form: extracted fields prefill from the stored thesis;
 * when the intake could not read a field it starts blank/unchecked so the
 * committee has to supply it.
 */
export function toIntakeForm(thesis: Thesis, missingFields: string[]): ThesisForm {
  const form = toForm(thesis);
  const missing = new Set(missingFields);
  if (missing.has("check_size_min_chf")) form.checkMin = "";
  if (missing.has("check_size_max_chf")) form.checkMax = "";
  if (missing.has("require_no_prior_vc")) form.requireNoPriorVc = false;
  if (missing.has("exclude_corporate_oss")) form.excludeCorporateOss = false;
  return form;
}

export function parseList(value: string): string[] {
  return value
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

export function toInput(thesis: Thesis, form: ThesisForm): ThesisInput {
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

/** Grouped "things we could not read": check size is one, policies is one. */
export function missingThingCount(missingFields: string[]): number {
  const groups = new Set<string>();
  for (const field of missingFields) {
    if (field === "check_size_min_chf" || field === "check_size_max_chf") groups.add("check");
    else if (field === "require_no_prior_vc" || field === "exclude_corporate_oss") groups.add("policy");
    else groups.add(field);
  }
  return groups.size;
}

const COUNT_WORDS = ["Zero", "One", "Two", "Three", "Four", "Five", "Six"];

export function countWord(n: number): string {
  return COUNT_WORDS[n] ?? String(n);
}

/** 250000 -> "250,000" (fixed locale so the demo renders identically everywhere). */
export function fmtChf(n: number): string {
  return n.toLocaleString("en-US");
}
