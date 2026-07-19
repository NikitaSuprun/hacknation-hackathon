/**
 * The in-memory demo store. Every MockDataSource mutation goes through
 * mutate(), so the UI (via useSyncExternalStore/react-query invalidation)
 * observes state exactly as it would from a real backend, the kanban
 * really advances, the memo really swaps, the score really moves.
 *
 * applyScenario() fast-forwards to a named point in the demo script; the
 * autopilot scrubber and ?beat= deep links replay through it.
 */
import type {
  CategoryKey,
  ChatMessage,
  IdealCandidateProfile,
  InterviewStage,
  Memo,
  OutreachRow,
  RankedVenture,
  ScoreSnapshot,
  ScoreWeights,
  StructuredAsks,
  Thesis,
  VentureGap,
  VentureTeamMember,
} from "@/lib/domain/types";
import { seedDB, type SeedDB } from "@/mocks/fixtures/seed";

/** The tokenized founder link used throughout the demo. */
export const DEMO_TOKEN = "demo";
/** Demo fund identity (fictional, self-referential on purpose). */
export const FUND_NAME = "Venture Hunt";
export const FUND_EMAIL = "partner@fund.example";

export interface InterviewState {
  stage: InterviewStage;
  consented: boolean;
  consent_text: string | null;
  structured: StructuredAsks | null;
  transcript: ChatMessage[];
}

/** The investor's thesis-intake journey (upload -> extraction -> review -> confirmed). */
export type ThesisIntakeStage = "empty" | "extracting" | "review" | "confirmed";

export interface ThesisIntakeState {
  stage: ThesisIntakeStage;
  /** What the committee provided: a website link or an uploaded file name. */
  source: string | null;
  /** Field names the mock "extraction" could not fill; the form marks them red. */
  missingFields: string[];
}

/** Thesis fields the scripted extraction cannot fill from a link or PDF. */
export const INTAKE_MISSING_FIELDS = [
  "check_size_min_chf",
  "check_size_max_chf",
  "require_no_prior_vc",
  "exclude_corporate_oss",
] as const;

export interface PostInterviewPatch {
  ventureId: string;
  /** Category scores confirmed/raised by the interview. */
  scores: Partial<Record<CategoryKey, number>>;
  confidence: number;
  fundingSignalAfter?: "confirmed_none";
}

export interface MockDB {
  thesis: Thesis;
  weights: ScoreWeights;
  /** Base rows, getRanking() re-ranks them under the current weights. */
  ventures: RankedVenture[];
  team: Record<string, VentureTeamMember[]>;
  /** Score history per venture, newest first (the /scores contract). */
  scoreHistory: Record<string, ScoreSnapshot[]>;
  /** Memo currently served per venture. */
  memos: Record<string, Memo>;
  /** Post-interview memo versions, swapped in by completeInterview(). */
  postMemos: Record<string, Memo>;
  gaps: Record<string, VentureGap[]>;
  outreach: OutreachRow[];
  ideal: IdealCandidateProfile;
  interview: InterviewState;
  thesisIntake: ThesisIntakeState;
  /** Ventures the committee kicked off the investment process for (mock-only). */
  investmentProcess: string[];
  postInterviewPatch: PostInterviewPatch | null;
}

function buildDB(seed: SeedDB): MockDB {
  return {
    thesis: seed.thesis,
    weights: seed.weights,
    ventures: seed.ventures,
    team: seed.team,
    scoreHistory: { ...seed.scoreHistory },
    memos: { ...seed.memos },
    postMemos: { ...seed.postMemos },
    gaps: seed.gaps,
    outreach: [...seed.outreach],
    ideal: seed.ideal,
    interview: {
      stage: "pending_consent",
      consented: false,
      consent_text: null,
      structured: null,
      transcript: [],
    },
    thesisIntake: {
      stage: "empty",
      source: null,
      missingFields: [...INTAKE_MISSING_FIELDS],
    },
    investmentProcess: [],
    postInterviewPatch: seed.postInterviewPatch,
  };
}

let db: MockDB = buildDB(seedDB());
const listeners = new Set<() => void>();
let version = 0;

export function getDB(): MockDB {
  return db;
}

export function getVersion(): number {
  return version;
}

export function mutate(fn: (db: MockDB) => void): void {
  fn(db);
  version += 1;
  for (const listener of listeners) listener();
}

export function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function resetDB(): void {
  db = buildDB(seedDB());
  version += 1;
  for (const listener of listeners) listener();
}

// Scenario fast-forwarding (demo scrubber / ?beat= deep links) lives in
// mocks/scenarios.ts, it replays mutations over this store.
