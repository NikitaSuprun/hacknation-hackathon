/**
 * Inbound "radar" intake — a tiny standalone client-side store. Deliberately
 * NOT part of the DataSource seam: it has no investor-side reads yet and the
 * founder page must work with zero auth or app shell.
 *
 * TODO(live mode): needs a `/v1/intake` endpoint upstream (the Starlette app)
 * that writes a bronze/candidate-intake row so the scoring pipeline can pick
 * inbound founders up alongside sourced ones. Until that endpoint exists,
 * submissions stay client-side in localStorage under "chosen.intakes".
 */

export interface IntakeSubmission {
  intake_id: string;
  created_at: string;
  github_url: string | null;
  linkedin_url: string | null;
  website_url: string | null;
  project_name: string | null;
  /** Founder's one-paragraph description; capped at 600 chars. */
  project_idea: string | null;
  team: { name: string; role: string | null; github_url: string | null }[];
  contact_email: string | null;
}

/** What the intake card collects — ids and timestamps are generated here. */
export type IntakeDraft = Omit<IntakeSubmission, "intake_id" | "created_at">;

export const IDEA_MAX_CHARS = 600;

const STORAGE_KEY = "chosen.intakes";

function readAll(): IntakeSubmission[] {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as IntakeSubmission[]) : [];
  } catch {
    return [];
  }
}

function makeId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return `intake_${crypto.randomUUID()}`;
  }
  return `intake_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 10)}`;
}

/**
 * Persist one intake locally and return it with a generated id.
 * ~400ms artificial latency so the pending state on the CTA is visible.
 */
export async function submitIntake(data: IntakeDraft): Promise<IntakeSubmission> {
  await new Promise((resolve) => setTimeout(resolve, 400));
  const record: IntakeSubmission = {
    ...data,
    project_idea: data.project_idea ? data.project_idea.slice(0, IDEA_MAX_CHARS) : null,
    intake_id: makeId(),
    created_at: new Date().toISOString(),
  };
  const all = readAll();
  all.push(record);
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(all));
  } catch {
    // Private mode / quota failures must not break the founder flow — the
    // record is still returned so the UI can confirm.
  }
  return record;
}

/** All locally stored intakes, oldest first — for the future admin surface. */
export function listIntakes(): IntakeSubmission[] {
  return readAll();
}
