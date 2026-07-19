/**
 * Zod mirrors of contracts/schemas/*.json + the gold view shapes.
 * Used by fixture-validation tests and by LiveDataSource when parsing
 * VARIANT columns (which the Statement Execution API returns as JSON strings).
 */
import { z } from "zod";
import { CATEGORY_KEYS, MEMO_SECTION_KEYS } from "@/lib/domain/types";

export const evidenceSchema = z.object({
  claim: z.string().min(1),
  source_url: z.string().min(1),
  source_type: z.string().nullish(),
  snippet: z.string().nullish(),
  weight: z.number().min(0).max(1).nullish(),
});

export const categoryScoreSchema = z.object({
  score: z.number().min(0).max(100).nullable(),
  method: z.string().min(1),
  rationale: z.string().nullish(),
  confidence: z.number().min(0).max(1).nullish(),
  evidence: z.array(evidenceSchema),
});

export const scoreBreakdownSchema = z.object({
  schema_version: z.number().int().min(1),
  categories: z.record(z.enum(CATEGORY_KEYS), categoryScoreSchema),
});

export const ventureStatusSchema = z.enum([
  "sourced",
  "scored",
  "shortlisted",
  "outreach",
  "interviewing",
  "passed",
  "archived",
]);

export const qualityTierSchema = z.enum(["scored", "needs_more_data"]);

export const fundingSignalSchema = z.enum(["none_found", "suspected", "confirmed_none"]);

export const outreachStatusSchema = z.enum([
  "draft",
  "approved",
  "sent",
  "bounced",
  "replied",
  "consented",
  "declined",
  "interview_scheduled",
  "interview_started",
  "interviewed",
  "closed",
  "opted_out",
  "expired",
]);

export const rankedVentureSchema = z.object({
  venture_id: z.string().uuid(),
  name: z.string().min(1),
  one_liner: z.string().min(1),
  status: ventureStatusSchema,
  quality_tier: qualityTierSchema.nullable(),
  market_tags: z.array(z.string()),
  final_score: z.number().min(0).max(100),
  confidence: z.number().min(0).max(1),
  ideal_match: z.number().min(0).max(100).nullable(),
  s_individual_experience: z.number().min(0).max(100).nullable(),
  s_schools: z.number().min(0).max(100).nullable(),
  s_network_ties: z.number().min(0).max(100).nullable(),
  s_prior_collaboration: z.number().min(0).max(100).nullable(),
  s_problem_realness: z.number().min(0).max(100).nullable(),
  s_product_defensibility: z.number().min(0).max(100).nullable(),
  s_market: z.number().min(0).max(100).nullable(),
  s_traction: z.number().min(0).max(100).nullable(),
  breakdown: scoreBreakdownSchema,
  scored_at: z.string(),
  funding_signal: fundingSignalSchema.nullable(),
});

export const ventureTeamMemberSchema = z.object({
  venture_id: z.string().uuid(),
  person_id: z.string().uuid(),
  full_name: z.string().min(1),
  headline: z.string().nullable(),
  github_login: z.string().nullable(),
  orcid: z.string().nullable(),
  linkedin_url: z.string().nullable(),
  affiliation: z.string().nullable(),
  avatar_url: z.string().nullable(),
  role_hint: z.string().nullable(),
  is_founder_guess: z.boolean(),
  weight: z.number().min(0).max(1),
  evidence: z.record(z.string(), z.unknown()).nullable(),
});

export const memoBulletSchema = z
  .object({
    text: z.string().min(1),
    evidence: z.array(evidenceSchema).optional(),
    missing: z.boolean().optional(),
    gap_field: z.string().nullish(),
  })
  .refine((b) => b.missing === true || (b.evidence?.length ?? 0) > 0, {
    message: "memo bullet must be cited or explicitly missing",
  });

export const memoSectionSchema = z.object({ bullets: z.array(memoBulletSchema) });

export const memoMarketSectionSchema = memoSectionSchema.extend({
  tam: z.string().nullish(),
  sam: z.string().nullish(),
  som: z.string().nullish(),
  assumptions: z.array(z.string()).optional(),
});

export const memoSectionsSchema = z.object({
  schema_version: z.number().int().min(1),
  company_snapshot: memoSectionSchema,
  investment_hypotheses: memoSectionSchema,
  swot: memoSectionSchema,
  team_and_history: memoSectionSchema,
  problem_and_product: memoSectionSchema,
  technology_and_defensibility: memoSectionSchema,
  market_tam_sam_som: memoMarketSectionSchema,
  competition: memoSectionSchema,
  traction_and_kpis: memoSectionSchema,
});

export const memoSchema = z.object({
  memo_id: z.string(),
  venture_id: z.string().uuid(),
  thesis_id: z.string(),
  sections: memoSectionsSchema,
  model_version: z.string(),
  status: z.string().nullable(),
  run_id: z.string().nullable(),
  generated_at: z.string(),
  is_latest: z.boolean(),
});

export const thesisSchema = z.object({
  thesis_id: z.string(),
  name: z.string().min(1),
  owner_email: z.string().email(),
  sectors: z.array(z.string()),
  geographies: z.array(z.string()),
  stages: z.array(z.string()),
  check_size_min_chf: z.number(),
  check_size_max_chf: z.number(),
  min_team: z.number().int(),
  max_team: z.number().int(),
  require_no_prior_vc: z.boolean(),
  exclude_corporate_oss: z.boolean(),
  notes: z.string().nullable(),
  is_active: z.boolean(),
  updated_at: z.string(),
  updated_by: z.string(),
});

export const scoreWeightsSchema = z.object({
  weights_id: z.string(),
  thesis_id: z.string(),
  version: z.number().int(),
  is_active: z.boolean(),
  w_individual_experience: z.number().min(0),
  w_schools: z.number().min(0),
  w_network_ties: z.number().min(0),
  w_prior_collaboration: z.number().min(0),
  w_problem_realness: z.number().min(0),
  w_product_defensibility: z.number().min(0),
  w_market: z.number().min(0),
  w_traction: z.number().min(0),
  w_ideal_match: z.number().min(0),
  updated_at: z.string(),
  updated_by: z.string(),
});

export const ventureGapSchema = z.object({
  venture_id: z.string().uuid(),
  category: z.string(),
  field: z.string().min(1),
  importance: z.number().min(0).max(1),
  question_text: z.string().min(1),
  created_at: z.string(),
});

export const outreachRowSchema = z.object({
  outreach_id: z.string(),
  venture_id: z.string().uuid(),
  person_id: z.string().uuid(),
  thesis_id: z.string(),
  channel: z.literal("email"),
  to_email: z.string().email(),
  subject: z.string().min(1),
  body: z.string().min(1),
  interview_url: z.string().nullish(),
  status: outreachStatusSchema,
  sent_at: z.string().nullable(),
  consent_at: z.string().nullable(),
  last_event_at: z.string().nullable(),
  token_expires_at: z.string().nullable(),
  question_plan: z.object({ questions: z.array(z.string()) }).nullable(),
  history: z.array(z.unknown()).nullable(),
  created_by: z.string(),
  updated_at: z.string(),
});

export const idealCandidateProfileSchema = z.object({
  schema_version: z.number().int().min(1),
  narrative: z.string().nullish(),
  education: z
    .array(
      z.object({
        institution: z.string().min(1),
        level: z.string().nullish(),
        field: z.string().nullish(),
      }),
    )
    .optional(),
  sectors: z.array(z.string()).optional(),
  keywords: z.array(z.string()).optional(),
  numeric_features: z.record(z.string(), z.number()),
  feature_weights: z.record(z.string(), z.number().min(0)).optional(),
});
