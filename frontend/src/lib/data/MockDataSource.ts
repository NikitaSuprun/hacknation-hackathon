/**
 * The presentation-demo data source: bundled fixtures, an in-memory store,
 * simulated latency (so skeleton states are real), canned streaming chat.
 * Zero network — nothing leaves the browser.
 */
import type { ChatStreamEvent, DataSource } from "@/lib/data/DataSource";
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
import { rerank } from "@/lib/ranking/rerank";
import { DEMO_TOKEN, FUND_EMAIL, FUND_NAME, getDB, mutate } from "@/mocks/state";
import { GRASPLAB_ID, buildSentOutreachRow } from "@/mocks/fixtures/seed";
import { INTERVIEW_SCRIPT } from "@/mocks/fixtures/chatScript";
import { completeInterviewMutation } from "@/mocks/scenarios";

let latencyDisabled = false;

/** The demo engine zeroes latency so autopilot beats land on time. */
export function setMockLatencyDisabled(disabled: boolean): void {
  latencyDisabled = disabled;
}

function latencyMs(): number {
  if (latencyDisabled) return 0;
  if (typeof window !== "undefined") {
    const params = new URLSearchParams(window.location.search);
    if (params.get("latency") === "0") return 0;
  }
  return 120 + Math.random() * 480;
}

const sleep = (ms: number) =>
  ms <= 0 ? Promise.resolve() : new Promise<void>((resolve) => setTimeout(resolve, ms));

export class MockDataSource implements DataSource {
  readonly requiresAuth = false;
  readonly mode = "mock" as const;

  private async simulate(): Promise<void> {
    await sleep(latencyMs());
  }

  // --- Investor ---

  async listTheses(): Promise<Thesis[]> {
    await this.simulate();
    return [getDB().thesis];
  }

  async saveThesis(input: ThesisInput): Promise<Thesis> {
    await this.simulate();
    mutate((db) => {
      db.thesis = {
        ...db.thesis,
        ...input,
        updated_at: new Date().toISOString(),
        updated_by: db.thesis.owner_email,
      };
    });
    return getDB().thesis;
  }

  async getWeights(_thesisId: string): Promise<ScoreWeights> {
    await this.simulate();
    return getDB().weights;
  }

  async saveWeights(_thesisId: string, weights: ScoreWeights): Promise<void> {
    await this.simulate();
    mutate((db) => {
      db.weights = {
        ...weights,
        version: db.weights.version + 1,
        updated_at: new Date().toISOString(),
      };
    });
  }

  async getIdealCandidate(_thesisId: string): Promise<IdealCandidateProfile> {
    await this.simulate();
    return getDB().ideal;
  }

  async saveIdealCandidate(
    _thesisId: string,
    profile: IdealCandidateProfile,
  ): Promise<RunHandle> {
    await this.simulate();
    mutate((db) => {
      db.ideal = profile;
    });
    return { runId: "mock-reembed" };
  }

  async getRanking(_thesisId: string): Promise<RankedVenture[]> {
    await this.simulate();
    const db = getDB();
    return rerank(db.ventures, db.weights);
  }

  async getVentureScores(ventureId: string): Promise<ScoreSnapshot[]> {
    await this.simulate();
    return getDB().scoreHistory[ventureId] ?? [];
  }

  async getVentureMemo(ventureId: string): Promise<Memo> {
    await this.simulate();
    const memo = getDB().memos[ventureId];
    if (!memo) throw new Error(`No memo for venture ${ventureId}`);
    return memo;
  }

  async getVentureTeam(ventureId: string): Promise<VentureTeamMember[]> {
    await this.simulate();
    return getDB().team[ventureId] ?? [];
  }

  async getVentureGaps(ventureId: string): Promise<VentureGap[]> {
    await this.simulate();
    return getDB().gaps[ventureId] ?? [];
  }

  async sendOutreach(ventureId: string, request: OutreachRequest): Promise<OutreachRow> {
    await this.simulate();
    const row = buildSentOutreachRow({ venture_id: ventureId, ...request });
    mutate((db) => {
      db.outreach = db.outreach.filter((o) => o.venture_id !== ventureId);
      db.outreach.push(row);
      const venture = db.ventures.find((v) => v.venture_id === ventureId);
      if (venture && venture.status !== "interviewing") venture.status = "outreach";
    });
    return row;
  }

  async rescoreVenture(_ventureId: string): Promise<RunHandle> {
    await this.simulate();
    return { runId: "mock-rescore" };
  }

  async listOutreach(_thesisId: string): Promise<OutreachRow[]> {
    await this.simulate();
    return getDB().outreach;
  }

  async getRunStatus(_handle: RunHandle): Promise<RunStatus> {
    await this.simulate();
    return "succeeded";
  }

  // --- Founder (token-authenticated) ---

  async getInterviewSession(token: string): Promise<InterviewBootstrap> {
    await this.simulate();
    if (token !== DEMO_TOKEN) {
      return {
        token,
        stage: "invalid",
        venture_name: "",
        founder_name: "",
        fund_name: FUND_NAME,
        fund_contact_email: FUND_EMAIL,
        why_contacted: "",
        data_sources: [],
        question_plan: [],
        structured: null,
        transcript: [],
      };
    }
    const db = getDB();
    const venture = db.ventures.find((v) => v.venture_id === GRASPLAB_ID);
    const founder = (db.team[GRASPLAB_ID] ?? []).find((m) => m.is_founder_guess);
    return {
      token,
      stage: db.interview.stage,
      venture_name: venture?.name ?? "GraspLab",
      founder_name: founder?.full_name ?? "Lena Fischer",
      fund_name: FUND_NAME,
      fund_contact_email: FUND_EMAIL,
      why_contacted:
        "We came across your repository grasp-anything and your paper GraspFM. Nothing here is an application — you were already selected for review.",
      data_sources: [
        { label: "GitHub — grasplab/grasp-anything", url: "https://github.com/grasplab/grasp-anything" },
        { label: "arXiv — GraspFM (2506.11111)", url: "https://arxiv.org/abs/2506.11111" },
        { label: "Zefix — GraspLab AG, Zurich", url: "https://www.zefix.ch/" },
      ],
      question_plan: (db.gaps[GRASPLAB_ID] ?? []).map((gap) => gap.question_text),
      structured: db.interview.structured,
      transcript: db.interview.transcript,
    };
  }

  async submitConsent(token: string, consent: ConsentPayload): Promise<void> {
    await this.simulate();
    if (token !== DEMO_TOKEN) throw new Error("Invalid link");
    mutate((db) => {
      db.interview.consented = consent.agreed;
      db.interview.consent_text = consent.consent_text;
      db.interview.stage = consent.agreed ? "consented" : "pending_consent";
      const row = db.outreach.find((o) => o.venture_id === GRASPLAB_ID);
      if (row && consent.agreed) {
        row.status = "consented";
        row.consent_at = new Date().toISOString();
      }
    });
  }

  async submitStructuredAsks(token: string, asks: StructuredAsks): Promise<void> {
    await this.simulate();
    if (token !== DEMO_TOKEN) throw new Error("Invalid link");
    mutate((db) => {
      db.interview.structured = asks;
    });
  }

  async uploadInterviewFile(
    token: string,
    kind: "cv" | "pitch",
    file: File,
  ): Promise<UploadedFileRef> {
    if (token !== DEMO_TOKEN) throw new Error("Invalid link");
    // Demo honesty: the file never leaves the browser — object URL only.
    return {
      kind,
      name: file.name,
      size_bytes: file.size,
      url: URL.createObjectURL(file),
    };
  }

  async *streamInterviewMessage(
    token: string,
    text: string,
    signal?: AbortSignal,
  ): AsyncIterable<ChatStreamEvent> {
    if (token !== DEMO_TOKEN) {
      yield { type: "error", message: "This link is not valid." };
      return;
    }
    const aiTurnIndex = getDB().interview.transcript.filter(
      (m) => m.role === "interviewer",
    ).length;
    if (text.trim()) {
      mutate((db) => {
        db.interview.transcript.push({
          id: `founder-${aiTurnIndex}-${Date.now()}`,
          role: "founder",
          text: text.trim(),
          at: new Date().toISOString(),
        });
        db.interview.stage = "in_progress";
        const row = db.outreach.find((o) => o.venture_id === GRASPLAB_ID);
        if (row && row.status === "consented") row.status = "interview_started";
      });
    }
    const turn = INTERVIEW_SCRIPT[aiTurnIndex];
    if (!turn) {
      yield { type: "done", messageId: "end-of-script" };
      return;
    }
    // "Thinking" pause, then word-chunk streaming with jitter.
    await sleep(latencyDisabled ? 60 : 700 + Math.random() * 500);
    const chunks = turn.ai.split(/(?<=\s)/);
    for (const chunk of chunks) {
      if (signal?.aborted) return;
      await sleep(latencyDisabled ? 4 : 22 + Math.random() * 30);
      yield { type: "token", text: chunk };
    }
    const messageId = `ai-${aiTurnIndex}`;
    mutate((db) => {
      db.interview.transcript.push({
        id: messageId,
        role: "interviewer",
        text: turn.ai,
        at: new Date().toISOString(),
      });
    });
    yield { type: "done", messageId };
  }

  async completeInterview(token: string): Promise<void> {
    await this.simulate();
    if (token !== DEMO_TOKEN) throw new Error("Invalid link");
    completeInterviewMutation();
  }
}
