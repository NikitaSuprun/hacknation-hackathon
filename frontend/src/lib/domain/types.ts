/**
 * TypeScript mirrors of the data contract (docs/contract.md + contracts/schemas/*.json).
 * The UI reads only the gold views; VARIANT columns arrive parsed (LiveDataSource
 * parses the JSON strings the Statement Execution API returns).
 */

// --- Status machines (DDL CHECK constraints are authoritative) ---

export type VentureStatus =
  | "sourced"
  | "scored"
  | "shortlisted"
  | "outreach"
  | "interviewing"
  | "passed"
  | "archived";

export type QualityTier = "scored" | "needs_more_data";

/** gold.candidate_pool.funding_signal — the ranked-list funding badge. */
export type FundingSignal = "none_found" | "suspected" | "confirmed_none";

export type OutreachStatus =
  | "draft"
  | "approved"
  | "sent"
  | "bounced"
  | "replied"
  | "consented"
  | "declined"
  | "interview_scheduled"
  | "interview_started"
  | "interviewed"
  | "closed"
  | "opted_out"
  | "expired";

// --- Scoring ---

export const CATEGORY_KEYS = [
  "individual_experience",
  "schools",
  "network_ties",
  "prior_collaboration",
  "problem_realness",
  "product_defensibility",
  "market",
  "traction",
  "ideal_match",
] as const;

export type CategoryKey = (typeof CATEGORY_KEYS)[number];

export const CATEGORY_LABELS: Record<CategoryKey, string> = {
  individual_experience: "Individual experience",
  schools: "Schools",
  network_ties: "Network ties",
  prior_collaboration: "Worked together before",
  problem_realness: "Problem realness",
  product_defensibility: "Product & defensibility",
  market: "Market",
  traction: "Traction",
  ideal_match: "Ideal-candidate match",
};

export interface Evidence {
  claim: string;
  source_url: string;
  source_type?: string | null;
  snippet?: string | null;
  weight?: number | null;
}

export interface CategoryScore {
  score: number | null;
  method: string;
  rationale?: string | null;
  confidence?: number | null;
  evidence: Evidence[];
}

export interface ScoreBreakdown {
  schema_version: number;
  categories: Partial<Record<CategoryKey, CategoryScore>>;
}

// --- gold.v_ranked_ventures (+ funding_signal joined from gold.candidate_pool) ---

export interface RankedVenture {
  venture_id: string;
  name: string;
  one_liner: string;
  status: VentureStatus;
  /** null for ventures the pipeline hasn't tiered yet (e.g. fresh hackathon signals). */
  quality_tier: QualityTier | null;
  market_tags: string[];
  final_score: number;
  confidence: number;
  ideal_match: number | null;
  s_individual_experience: number | null;
  s_schools: number | null;
  s_network_ties: number | null;
  s_prior_collaboration: number | null;
  s_problem_realness: number | null;
  s_product_defensibility: number | null;
  s_market: number | null;
  s_traction: number | null;
  breakdown: ScoreBreakdown;
  scored_at: string;
  funding_signal: FundingSignal | null;
}

// --- gold.v_venture_team ---

export interface VentureTeamMember {
  venture_id: string;
  person_id: string;
  full_name: string;
  headline: string | null;
  github_login: string | null;
  orcid: string | null;
  linkedin_url: string | null;
  affiliation: string | null;
  avatar_url: string | null;
  role_hint: string | null;
  is_founder_guess: boolean;
  weight: number;
  evidence: Record<string, unknown> | null;
}

// --- gold.thesis ---

export interface Thesis {
  thesis_id: string;
  name: string;
  owner_email: string;
  sectors: string[];
  geographies: string[];
  stages: string[];
  check_size_min_chf: number;
  check_size_max_chf: number;
  min_team: number;
  max_team: number;
  require_no_prior_vc: boolean;
  exclude_corporate_oss: boolean;
  notes: string | null;
  is_active: boolean;
  updated_at: string;
  updated_by: string;
}

export type ThesisInput = Omit<Thesis, "updated_at" | "updated_by">;

// --- gold.score_weights ---

export interface ScoreWeights {
  weights_id: string;
  thesis_id: string;
  version: number;
  is_active: boolean;
  w_individual_experience: number;
  w_schools: number;
  w_network_ties: number;
  w_prior_collaboration: number;
  w_problem_realness: number;
  w_product_defensibility: number;
  w_market: number;
  w_traction: number;
  w_ideal_match: number;
  updated_at: string;
  updated_by: string;
}

/** Weight column for a category — the names line up as w_<category>. */
export function weightKey(category: CategoryKey): keyof ScoreWeights {
  return `w_${category}` as keyof ScoreWeights;
}

// --- gold.memo (sections per memo.schema.json: 9 fixed sections) ---

export interface MemoBullet {
  text: string;
  evidence?: Evidence[];
  missing?: boolean;
  gap_field?: string | null;
}

export interface MemoSection {
  bullets: MemoBullet[];
}

export interface MemoMarketSection extends MemoSection {
  tam?: string | null;
  sam?: string | null;
  som?: string | null;
  assumptions?: string[];
}

export const MEMO_SECTION_KEYS = [
  "company_snapshot",
  "investment_hypotheses",
  "swot",
  "team_and_history",
  "problem_and_product",
  "technology_and_defensibility",
  "market_tam_sam_som",
  "competition",
  "traction_and_kpis",
] as const;

export type MemoSectionKey = (typeof MEMO_SECTION_KEYS)[number];

export const MEMO_SECTION_LABELS: Record<MemoSectionKey, string> = {
  company_snapshot: "Company snapshot",
  investment_hypotheses: "Investment hypotheses",
  swot: "SWOT",
  team_and_history: "Team & history",
  problem_and_product: "Problem & product",
  technology_and_defensibility: "Technology & defensibility",
  market_tam_sam_som: "Market (TAM / SAM / SOM)",
  competition: "Competition",
  traction_and_kpis: "Traction & KPIs",
};

export interface MemoSections {
  schema_version: number;
  company_snapshot: MemoSection;
  investment_hypotheses: MemoSection;
  swot: MemoSection;
  team_and_history: MemoSection;
  problem_and_product: MemoSection;
  technology_and_defensibility: MemoSection;
  market_tam_sam_som: MemoMarketSection;
  competition: MemoSection;
  traction_and_kpis: MemoSection;
}

export interface Memo {
  memo_id: string;
  venture_id: string;
  thesis_id: string;
  sections: MemoSections;
  model_version: string;
  status: string | null;
  run_id: string | null;
  generated_at: string;
  is_latest: boolean;
}

// --- gold.venture_gaps (the missing-data list / interview question plan) ---

export interface VentureGap {
  venture_id: string;
  category: CategoryKey | string;
  field: string;
  importance: number;
  question_text: string;
  created_at: string;
}

// --- gold.outreach ---

export interface OutreachRow {
  outreach_id: string;
  venture_id: string;
  person_id: string;
  thesis_id: string;
  channel: "email";
  to_email: string;
  subject: string;
  body: string;
  /** Returned by the live send endpoint so the demo can open the founder page without an inbox. */
  interview_url?: string | null;
  status: OutreachStatus;
  sent_at: string | null;
  consent_at: string | null;
  last_event_at: string | null;
  token_expires_at: string | null;
  question_plan: { questions: string[] } | null;
  history: unknown[] | null;
  created_by: string;
  updated_at: string;
}

export interface OutreachRequest {
  to_email: string;
  subject: string;
  body: string;
}

// --- gold.ideal_candidate.profile_json (ideal.schema.json) ---

export interface IdealCandidateProfile {
  schema_version: number;
  narrative?: string | null;
  education?: { institution: string; level?: string | null; field?: string | null }[];
  sectors?: string[];
  keywords?: string[];
  numeric_features: Record<string, number>;
  feature_weights?: Record<string, number>;
}

// --- Interview (founder side; UI-level shapes over gold.interview + outreach token) ---

export interface ChatMessage {
  id: string;
  role: "interviewer" | "founder";
  text: string;
  at: string;
}

export interface UploadedFileRef {
  kind: "cv" | "pitch";
  name: string;
  size_bytes: number;
  /** Demo mode: browser object URL; live mode: Supabase storage path. */
  url: string | null;
}

export interface StructuredAsks {
  linkedin_url: string | null;
  github_url: string | null;
  cv_file: UploadedFileRef | null;
  pitch_file: UploadedFileRef | null;
  traction_notes: string | null;
}

export interface ConsentPayload {
  agreed: boolean;
  consent_text: string;
}

export type InterviewStage =
  | "pending_consent"
  | "consented"
  | "in_progress"
  | "completed"
  | "invalid"
  | "expired";

export interface InterviewBootstrap {
  token: string;
  stage: InterviewStage;
  venture_name: string;
  founder_name: string;
  fund_name: string;
  fund_contact_email: string;
  /** Live mode: the server's verbatim consent prompt (first chat message answers it). */
  consent_prompt?: string | null;
  /** GDPR Art. 14 transparency: why this person was contacted. */
  why_contacted: string;
  /** What public data the fund holds, with sources. */
  data_sources: { label: string; url: string }[];
  question_plan: string[];
  structured: StructuredAsks | null;
  transcript: ChatMessage[];
}

/** interview.schema.json — consent-based facts filling scored gaps. */
export interface InterviewExtracted {
  schema_version: number;
  education?: { institution: string; degree?: string | null; field?: string | null; start_year?: number | null; end_year?: number | null }[];
  career?: { organization: string; role?: string | null; start_year?: number | null; end_year?: number | null }[];
  team_commitment?: { status: "full_time" | "part_time" | "exploring" | "unknown"; notes?: string | null };
  traction_claims?: { metric: string; value: string; as_of?: string | null; verified: boolean }[];
  funding_status?: { raised_before: boolean | null; details?: string | null };
}

// --- Async runs (Jobs run-now + polling) ---

export interface RunHandle {
  runId: string;
}

export type RunStatus = "pending" | "running" | "succeeded" | "failed";
