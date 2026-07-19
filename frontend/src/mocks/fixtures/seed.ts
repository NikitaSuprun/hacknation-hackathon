/**
 * Assembles the typed demo database from the generated contract fixtures
 * (GraspLab + VoiceLab and friends) plus the hand-authored extra ventures.
 * Every fixture venture with a latest score and pool inclusion is assembled
 * generically, GraspLab is then special-cased to its PRE-interview state:
 * traction/market/defensibility are degraded on exactly the gap fields, and
 * the interview restores the fixture `is_latest` values, so the re-score
 * beat is arithmetically honest.
 */
import * as GEN from "./generated";
import { EXTRA_GAPS, EXTRA_MEMOS, EXTRA_TEAM, EXTRA_VENTURES } from "./extraVentures";
import { GRASPLAB_MEMO_POST_SECTIONS, GRASPLAB_MEMO_PRE_SECTIONS } from "./memos";
import { categoryScoresOf, computeFinalScore } from "@/lib/ranking/rerank";
import type {
  CategoryKey,
  IdealCandidateProfile,
  Memo,
  MemoSections,
  OutreachRow,
  RankedVenture,
  ScoreBreakdown,
  ScoreSnapshot,
  ScoreWeights,
  Thesis,
  VentureGap,
  VentureTeamMember,
} from "@/lib/domain/types";
import type { PostInterviewPatch } from "@/mocks/state";

export const GRASPLAB_ID = "81963541-592e-5edf-8b82-9fe0b26b4555";
export const LENA_PERSON_ID = "11111111-1111-4111-8111-000000000001";

type Raw = Record<string, unknown>;

const rawThesis = GEN.theses[0] as Raw;
const rawWeights = GEN.scoreWeights[0] as Raw;
const rawOutreach = GEN.outreach[0] as Raw;
const rawMemo = GEN.memos[0] as Raw;
const rawIdeal = GEN.idealCandidates[0] as Raw;

const latestScoreByVenture = new Map<string, Raw>();
for (const score of GEN.ventureScores as Raw[]) {
  if (score.is_latest === true) latestScoreByVenture.set(score.venture_id as string, score);
}

const poolByVenture = new Map<string, Raw>();
for (const pool of GEN.candidatePool as Raw[]) {
  poolByVenture.set(pool.venture_id as string, pool);
}

/** Pre-interview downgrades on exactly the gap fields (restored by the interview). */
const PRE_INTERVIEW_SCORES: Partial<Record<CategoryKey, number>> = {
  traction: 46,
  market: 58,
  product_defensibility: 78,
};

const PRE_INTERVIEW_RATIONALES: Partial<Record<CategoryKey, string>> = {
  traction:
    "8,200 stars in 4 months is top-decile OSS adoption, but stars are not users, revenue and pilots unverified; score capped until confirmed in interview.",
  market:
    "Warehouse-automation demand signals are strong, but no bottom-up TAM/SAM/SOM computed, first-segment sizing missing.",
  product_defensibility:
    "Own foundation model with published training recipe, not an API wrapper. Open question: terms of the ETH IP license.",
};

/** Generic gold.venture + latest gold.venture_score + candidate_pool join (mirrors app/store.py). */
function assembleVenture(rawVenture: Raw): RankedVenture | null {
  const ventureId = rawVenture.venture_id as string;
  const score = latestScoreByVenture.get(ventureId);
  if (!score) return null;
  const pool = poolByVenture.get(ventureId);
  if (pool && pool.included === false) return null;
  const venture: RankedVenture = {
    venture_id: ventureId,
    name: rawVenture.name as string,
    one_liner: rawVenture.one_liner as string,
    status: rawVenture.status as RankedVenture["status"],
    quality_tier: (rawVenture.quality_tier as RankedVenture["quality_tier"]) ?? null,
    market_tags: (rawVenture.market_tags as string[]) ?? [],
    final_score: 0, // computed below from categories + default weights

    confidence: score.confidence as number,
    ideal_match: (score.ideal_match as number | null) ?? null,
    s_individual_experience: (score.s_individual_experience as number | null) ?? null,
    s_schools: (score.s_schools as number | null) ?? null,
    s_network_ties: (score.s_network_ties as number | null) ?? null,
    s_prior_collaboration: (score.s_prior_collaboration as number | null) ?? null,
    s_problem_realness: (score.s_problem_realness as number | null) ?? null,
    s_product_defensibility: (score.s_product_defensibility as number | null) ?? null,
    s_market: (score.s_market as number | null) ?? null,
    s_traction: (score.s_traction as number | null) ?? null,
    breakdown: structuredClone(score.breakdown) as ScoreBreakdown,
    scored_at: score.scored_at as string,
    funding_signal: (pool?.funding_signal as RankedVenture["funding_signal"]) ?? null,
  };
  venture.final_score = computeFinalScore(
    categoryScoresOf(venture),
    rawWeights as unknown as ScoreWeights,
  );
  return venture;
}

function applyGrasplabPreInterview(venture: RankedVenture): RankedVenture {
  const downgraded: RankedVenture = {
    ...venture,
    status: "scored",
    confidence: 0.7,
    s_product_defensibility: PRE_INTERVIEW_SCORES.product_defensibility!,
    s_market: PRE_INTERVIEW_SCORES.market!,
    s_traction: PRE_INTERVIEW_SCORES.traction!,
  };
  for (const [key, score] of Object.entries(PRE_INTERVIEW_SCORES)) {
    const cat = downgraded.breakdown.categories[key as CategoryKey];
    if (cat) {
      cat.score = score;
      cat.confidence = 0.55;
      const rationale = PRE_INTERVIEW_RATIONALES[key as CategoryKey];
      if (rationale) cat.rationale = rationale;
    }
  }
  downgraded.final_score = computeFinalScore(
    categoryScoresOf(downgraded),
    rawWeights as unknown as ScoreWeights,
  );
  return downgraded;
}

function fixtureVentures(): RankedVenture[] {
  const assembled: RankedVenture[] = [];
  for (const rawVenture of GEN.ventures as Raw[]) {
    const venture = assembleVenture(rawVenture);
    if (!venture) continue;
    assembled.push(
      venture.venture_id === GRASPLAB_ID ? applyGrasplabPreInterview(venture) : venture,
    );
  }
  return assembled;
}

function fixtureTeams(): Record<string, VentureTeamMember[]> {
  const persons = GEN.persons as Raw[];
  const teams: Record<string, VentureTeamMember[]> = {};
  for (const member of GEN.ventureMembers as Raw[]) {
    const ventureId = member.venture_id as string;
    const person = persons.find((p) => p.person_id === member.person_id) ?? {};
    (teams[ventureId] ??= []).push({
      venture_id: ventureId,
      person_id: member.person_id as string,
      full_name: (person.full_name as string) ?? "Unknown",
      headline: (person.headline as string | null) ?? null,
      github_login: (person.github_login as string | null) ?? null,
      orcid: (person.orcid as string | null) ?? null,
      linkedin_url: (person.linkedin_url as string | null) ?? null,
      affiliation: (person.affiliation as string | null) ?? null,
      avatar_url: (person.avatar_url as string | null) ?? null,
      role_hint: (member.role_hint as string | null) ?? null,
      is_founder_guess: Boolean(member.is_founder_guess),
      weight: member.weight as number,
      evidence: (member.evidence as Record<string, unknown> | null) ?? null,
    });
  }
  return teams;
}

function fixtureGaps(): Record<string, VentureGap[]> {
  const gaps: Record<string, VentureGap[]> = {};
  for (const gap of GEN.ventureGaps as Raw[]) {
    const ventureId = gap.venture_id as string;
    (gaps[ventureId] ??= []).push({
      venture_id: ventureId,
      category: gap.category as string,
      field: gap.field as string,
      importance: gap.importance as number,
      question_text: gap.question_text as string,
      created_at: gap.created_at as string,
    });
  }
  return gaps;
}

function grasplabMemo(id: string, sections: MemoSections, generatedAt?: string): Memo {
  return {
    memo_id: id,
    venture_id: GRASPLAB_ID,
    thesis_id: rawMemo.thesis_id as string,
    sections: structuredClone(sections),
    model_version: rawMemo.model_version as string,
    status: (rawMemo.status as string | null) ?? null,
    run_id: (rawMemo.run_id as string | null) ?? null,
    generated_at: generatedAt ?? (rawMemo.generated_at as string),
    is_latest: true,
  };
}

/**
 * The outreach row minted by "Send outreach", provenance-first body per the
 * GDPR Art. 14 requirement in the reference doc.
 */
export function buildSentOutreachRow(overrides: Partial<OutreachRow> = {}): OutreachRow {
  const now = new Date().toISOString();
  return {
    outreach_id: `outreach-${Math.random().toString(36).slice(2, 10)}`,
    venture_id: GRASPLAB_ID,
    person_id: LENA_PERSON_ID,
    thesis_id: rawThesis.thesis_id as string,
    channel: "email",
    to_email: (rawOutreach.to_email as string) ?? "lena.fischer@ethz.ch",
    subject: (rawOutreach.subject as string) ?? "Your work on GraspFM",
    body:
      (rawOutreach.body as string) ??
      "We came across your repository grasp-anything and your paper GraspFM...",
    interview_url: "/interview/demo",
    status: "sent",
    sent_at: now,
    consent_at: null,
    last_event_at: now,
    token_expires_at: new Date(Date.now() + 14 * 24 * 3600 * 1000).toISOString(),
    question_plan: {
      // The seed merge replaces GraspLab's generated gaps with the authored
      // five-question plan, mirror that here so the outreach row agrees.
      questions: (EXTRA_GAPS[GRASPLAB_ID] ?? fixtureGaps()[GRASPLAB_ID] ?? []).map(
        (gap) => gap.question_text,
      ),
    },
    history: null,
    created_by: rawThesis.owner_email as string,
    updated_at: now,
    ...overrides,
  };
}

export interface SeedDB {
  thesis: Thesis;
  weights: ScoreWeights;
  ventures: RankedVenture[];
  team: Record<string, VentureTeamMember[]>;
  scoreHistory: Record<string, ScoreSnapshot[]>;
  memos: Record<string, Memo>;
  postMemos: Record<string, Memo>;
  gaps: Record<string, VentureGap[]>;
  outreach: OutreachRow[];
  ideal: IdealCandidateProfile;
  postInterviewPatch: PostInterviewPatch | null;
}

/** Score snapshot of a venture's CURRENT values, used to seed history. */
export function snapshotOf(venture: RankedVenture, scoreId: string): ScoreSnapshot {
  return {
    score_id: scoreId,
    venture_id: venture.venture_id,
    final_score: venture.final_score,
    confidence: venture.confidence,
    ideal_match: venture.ideal_match,
    s_individual_experience: venture.s_individual_experience,
    s_schools: venture.s_schools,
    s_network_ties: venture.s_network_ties,
    s_prior_collaboration: venture.s_prior_collaboration,
    s_problem_realness: venture.s_problem_realness,
    s_product_defensibility: venture.s_product_defensibility,
    s_market: venture.s_market,
    s_traction: venture.s_traction,
    breakdown: structuredClone(venture.breakdown),
    scored_at: venture.scored_at,
  };
}

export function seedDB(): SeedDB {
  const grasplabLatest = latestScoreByVenture.get(GRASPLAB_ID)!;
  const ventures = [...fixtureVentures(), ...EXTRA_VENTURES];
  const scoreHistory: Record<string, ScoreSnapshot[]> = {};
  for (const venture of ventures) {
    scoreHistory[venture.venture_id] = [snapshotOf(venture, `score-${venture.venture_id}-1`)];
  }
  const seed: SeedDB = {
    thesis: rawThesis as unknown as Thesis,
    weights: rawWeights as unknown as ScoreWeights,
    ventures,
    team: { ...fixtureTeams(), ...EXTRA_TEAM },
    scoreHistory,
    memos: {
      [GRASPLAB_ID]: grasplabMemo("memo-grasplab-pre", GRASPLAB_MEMO_PRE_SECTIONS),
      ...EXTRA_MEMOS,
    },
    postMemos: {
      [GRASPLAB_ID]: grasplabMemo(
        "memo-grasplab-post",
        GRASPLAB_MEMO_POST_SECTIONS,
        "2026-07-16T10:20:00+00:00",
      ),
    },
    gaps: { ...fixtureGaps(), ...EXTRA_GAPS },
    outreach: [],
    ideal: rawIdeal.profile_json as unknown as IdealCandidateProfile,
    // The interview restores the fixture is_latest values, nothing invented.
    postInterviewPatch: {
      ventureId: GRASPLAB_ID,
      scores: {
        traction: grasplabLatest.s_traction as number,
        market: grasplabLatest.s_market as number,
        product_defensibility: grasplabLatest.s_product_defensibility as number,
      },
      confidence: grasplabLatest.confidence as number,
      fundingSignalAfter: "confirmed_none",
    },
  };
  // Fresh references on every call so resetDB() truly resets.
  return structuredClone(seed);
}
