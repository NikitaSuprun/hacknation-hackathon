import type {
  ConsentPayload,
  IdealCandidateProfile,
  InterviewBootstrap,
  Memo,
  OutreachRequest,
  OutreachRow,
  RankedVenture,
  RunHandle,
  RunStatus,
  ScoreSnapshot,
  ScoreWeights,
  StructuredAsks,
  Thesis,
  ThesisInput,
  UploadedFileRef,
  VentureGap,
  VentureTeamMember,
} from "@/lib/domain/types";

export type ChatStreamEvent =
  | { type: "token"; text: string }
  | { type: "done"; messageId: string }
  | { type: "error"; message: string };

/**
 * The mock/live seam. MockDataSource serves bundled fixtures with simulated
 * latency (fully client-side, the presentation demo); LiveDataSource calls
 * the Supabase edge-function proxy over Databricks. Same interface, chosen at
 * boot by lib/data/index.ts, the app cannot tell the difference.
 */
export interface DataSource {
  /** Live gates the investor routes on a Supabase session; mock bypasses by construction. */
  readonly requiresAuth: boolean;
  readonly mode: "mock" | "live";

  // Investor (Supabase JWT in live mode)
  listTheses(): Promise<Thesis[]>;
  saveThesis(input: ThesisInput): Promise<Thesis>;
  getWeights(thesisId: string): Promise<ScoreWeights>;
  saveWeights(thesisId: string, weights: ScoreWeights): Promise<void>;
  getIdealCandidate(thesisId: string): Promise<IdealCandidateProfile>;
  saveIdealCandidate(thesisId: string, profile: IdealCandidateProfile): Promise<RunHandle>;
  getRanking(thesisId: string): Promise<RankedVenture[]>;
  /** Full score history, newest first, [0] is current, [1] the pre-interview state. */
  getVentureScores(ventureId: string): Promise<ScoreSnapshot[]>;
  getVentureMemo(ventureId: string): Promise<Memo>;
  getVentureTeam(ventureId: string): Promise<VentureTeamMember[]>;
  getVentureGaps(ventureId: string): Promise<VentureGap[]>;
  sendOutreach(ventureId: string, request: OutreachRequest): Promise<OutreachRow>;
  rescoreVenture(ventureId: string): Promise<RunHandle>;
  listOutreach(thesisId: string): Promise<OutreachRow[]>;
  getRunStatus(handle: RunHandle): Promise<RunStatus>;

  // Founder (outreach token is the credential, never account auth)
  getInterviewSession(token: string): Promise<InterviewBootstrap>;
  submitConsent(token: string, consent: ConsentPayload): Promise<void>;
  submitStructuredAsks(token: string, asks: StructuredAsks): Promise<void>;
  uploadInterviewFile(token: string, kind: "cv" | "pitch", file: File): Promise<UploadedFileRef>;
  streamInterviewMessage(
    token: string,
    text: string,
    signal?: AbortSignal,
  ): AsyncIterable<ChatStreamEvent>;
  completeInterview(token: string): Promise<void>;
}
