/**
 * The real data source: the in-repo Starlette app (`python -m app serve`)
 * exposing /v1 over Databricks (or its fixtures mode). Same-origin in
 * production (bundle served by the app); the Vite dev server proxies /v1.
 *
 * Wire conventions (see app/api.py): investor routes take a bearer session
 * token; interview routes take the URL token + an X-Interview-Session header;
 * VARIANT columns arrive as JSON strings; chat is turn-based JSON — this
 * class fakes token streaming client-side so the UI matches mock mode.
 */
import type { ChatStreamEvent, DataSource } from "@/lib/data/DataSource";
import { API_BASE, clearSessionToken, getSessionToken } from "@/lib/auth";
import { memoSectionsSchema, scoreBreakdownSchema } from "@/lib/domain/schemas";
import type {
  ConsentPayload,
  IdealCandidateProfile,
  InterviewBootstrap,
  Memo,
  MemoSections,
  OutreachRequest,
  OutreachRow,
  RankedVenture,
  RunHandle,
  RunStatus,
  ScoreBreakdown,
  ScoreWeights,
  StructuredAsks,
  Thesis,
  ThesisInput,
  UploadedFileRef,
  VentureGap,
  VentureTeamMember,
} from "@/lib/domain/types";

/** VARIANT columns arrive as JSON strings from the Statement Execution API. */
function parseVariant<T>(value: unknown): T | null {
  if (value == null) return null;
  return (typeof value === "string" ? JSON.parse(value) : value) as T;
}

const INTERVIEW_SESSION_KEY = "chosen.interview-session";

function interviewSessionId(): string {
  let id = sessionStorage.getItem(INTERVIEW_SESSION_KEY);
  if (!id) {
    id = Array.from(crypto.getRandomValues(new Uint8Array(16)), (b) =>
      b.toString(16).padStart(2, "0"),
    ).join("");
    sessionStorage.setItem(INTERVIEW_SESSION_KEY, id);
  }
  return id;
}

const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

interface ThesisEnvelope {
  theses: Thesis[];
  weights: ScoreWeights[];
  ideals: Record<string, unknown>[];
}

export class LiveDataSource implements DataSource {
  readonly requiresAuth = true;
  readonly mode = "live" as const;

  private async request<T>(path: string, init?: RequestInit): Promise<T> {
    const token = getSessionToken();
    const response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(init?.headers ?? {}),
      },
    });
    if (response.status === 401) {
      clearSessionToken();
      throw new Error("Session expired — sign in again.");
    }
    if (!response.ok) {
      const body = (await response.json().catch(() => null)) as { error?: string } | null;
      throw new Error(body?.error ?? `${path} failed (${response.status})`);
    }
    return (await response.json()) as T;
  }

  private thesisEnvelope(): Promise<ThesisEnvelope> {
    return this.request<ThesisEnvelope>("/v1/thesis");
  }

  // --- Investor ---

  async listTheses(): Promise<Thesis[]> {
    return (await this.thesisEnvelope()).theses;
  }

  saveThesis(input: ThesisInput): Promise<Thesis> {
    return this.request("/v1/thesis", { method: "POST", body: JSON.stringify(input) });
  }

  async getWeights(thesisId: string): Promise<ScoreWeights> {
    const { weights } = await this.thesisEnvelope();
    const row = weights.find((w) => w.thesis_id === thesisId && w.is_active) ?? weights[0];
    if (!row) throw new Error("No weights configured for this thesis.");
    return row;
  }

  async saveWeights(thesisId: string, weights: ScoreWeights): Promise<void> {
    await this.request(`/v1/thesis/${thesisId}/weights`, {
      method: "PUT",
      body: JSON.stringify(weights),
    });
  }

  async getIdealCandidate(thesisId: string): Promise<IdealCandidateProfile> {
    const { ideals } = await this.thesisEnvelope();
    const row = ideals.find((r) => r.thesis_id === thesisId && r.is_active) ?? ideals[0];
    if (!row) throw new Error("No ideal-candidate profile for this thesis.");
    const profile = parseVariant<IdealCandidateProfile>(row.profile_json);
    if (!profile) throw new Error("Ideal-candidate profile is empty.");
    return profile;
  }

  async saveIdealCandidate(
    thesisId: string,
    profile: IdealCandidateProfile,
  ): Promise<RunHandle> {
    // Synchronous server-side (re-render + re-embed inline) — no job to poll.
    await this.request(`/v1/thesis/${thesisId}/ideal-candidate`, {
      method: "PUT",
      body: JSON.stringify(profile),
    });
    return { runId: "sync" };
  }

  async getRanking(thesisId: string): Promise<RankedVenture[]> {
    const { ventures } = await this.request<{ ventures: Record<string, unknown>[] }>(
      `/v1/ranking?thesis_id=${encodeURIComponent(thesisId)}`,
    );
    return ventures.map((row) => ({
      ...(row as unknown as RankedVenture),
      quality_tier: (row.quality_tier as RankedVenture["quality_tier"]) ?? null,
      market_tags: parseVariant<string[]>(row.market_tags) ?? [],
      breakdown: scoreBreakdownSchema.parse(
        parseVariant(row.breakdown),
      ) as unknown as ScoreBreakdown,
      // Ranking rows don't carry the pool's funding_signal — badge renders only when present.
      funding_signal: (row.funding_signal as RankedVenture["funding_signal"]) ?? null,
    }));
  }

  async getVentureScores(ventureId: string): Promise<ScoreBreakdown> {
    const { scores } = await this.request<{ scores: Record<string, unknown>[] }>(
      `/v1/venture/${ventureId}/scores`,
    );
    const latest = scores[0];
    if (!latest) throw new Error("No scores for this venture yet.");
    return scoreBreakdownSchema.parse(
      parseVariant(latest.breakdown),
    ) as unknown as ScoreBreakdown;
  }

  async getVentureMemo(ventureId: string): Promise<Memo> {
    const row = await this.request<Record<string, unknown>>(`/v1/venture/${ventureId}/memo`);
    return {
      ...(row as unknown as Memo),
      sections: memoSectionsSchema.parse(
        parseVariant(row.sections),
      ) as unknown as MemoSections,
    };
  }

  async getVentureTeam(ventureId: string): Promise<VentureTeamMember[]> {
    const { team } = await this.request<{ team: Record<string, unknown>[] }>(
      `/v1/venture/${ventureId}/team`,
    );
    return team.map((member) => ({
      ...(member as unknown as VentureTeamMember),
      evidence: parseVariant<Record<string, unknown>>(member.evidence),
    }));
  }

  async getVentureGaps(_ventureId: string): Promise<VentureGap[]> {
    // No /gaps endpoint upstream — the memo's `missing` bullets carry the gap
    // list in live mode; the UI treats this as a supplement.
    return [];
  }

  async sendOutreach(ventureId: string, _request: OutreachRequest): Promise<OutreachRow> {
    // The server composes subject/body itself (provenance + opt-out included).
    const result = await this.request<{
      outreach_id: string;
      status: OutreachRow["status"];
      to_email: string;
      interview_url: string;
    }>(`/v1/venture/${ventureId}/outreach`, { method: "POST", body: JSON.stringify({}) });
    const { outreach } = await this.request<{ outreach: Record<string, unknown>[] }>(
      "/v1/outreach",
    );
    const row = outreach.find((o) => o.outreach_id === result.outreach_id);
    return {
      ...(row as unknown as OutreachRow),
      question_plan: row
        ? parseVariant<{ questions: string[] }>(row.question_plan)
        : null,
      interview_url: result.interview_url,
    };
  }

  async rescoreVenture(ventureId: string): Promise<RunHandle> {
    const result = await this.request<{ status: string; score_id: string | null }>(
      `/v1/venture/${ventureId}/rescore`,
      { method: "POST", body: JSON.stringify({}) },
    );
    return { runId: result.score_id ?? "rescore" };
  }

  async listOutreach(thesisId: string): Promise<OutreachRow[]> {
    const { outreach } = await this.request<{ outreach: Record<string, unknown>[] }>(
      `/v1/outreach?thesis_id=${encodeURIComponent(thesisId)}`,
    );
    return outreach.map((row) => ({
      ...(row as unknown as OutreachRow),
      question_plan: parseVariant<{ questions: string[] }>(row.question_plan),
      history: parseVariant<unknown[]>(row.history),
    }));
  }

  async getRunStatus(_handle: RunHandle): Promise<RunStatus> {
    return "succeeded";
  }

  // --- Founder (outreach token + X-Interview-Session header) ---

  private async interviewRequest<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await fetch(`${API_BASE}/v1/interview${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        "X-Interview-Session": interviewSessionId(),
        ...(init?.headers ?? {}),
      },
    });
    if (!response.ok) {
      const body = (await response.json().catch(() => null)) as { error?: string } | null;
      const error = new Error(body?.error ?? `Interview request failed (${response.status})`);
      (error as Error & { status?: number }).status = response.status;
      throw error;
    }
    return (await response.json()) as T;
  }

  async getInterviewSession(token: string): Promise<InterviewBootstrap> {
    try {
      const session = await this.interviewRequest<{
        venture_name: string;
        fund_name: string;
        why_contacted: string | null;
        consent_prompt: string;
        consented: boolean;
        questions_total: number;
        transcript: unknown;
      }>(`/${token}`);
      const transcript =
        parseVariant<{ role: string; text: string; at: string }[]>(session.transcript) ?? [];
      return {
        token,
        stage: session.consented
          ? transcript.length > 0
            ? "in_progress"
            : "consented"
          : "pending_consent",
        venture_name: session.venture_name,
        founder_name: "",
        fund_name: session.fund_name,
        fund_contact_email: "",
        consent_prompt: session.consent_prompt,
        why_contacted: session.why_contacted ?? "",
        data_sources: [],
        question_plan: [],
        structured: null,
        transcript: transcript.map((message, i) => ({
          id: `live-${i}`,
          role: message.role === "assistant" ? "interviewer" : "founder",
          text: message.text,
          at: message.at ?? new Date().toISOString(),
        })),
      };
    } catch (error) {
      const status = (error as Error & { status?: number }).status;
      return {
        token,
        stage: status === 410 ? "expired" : "invalid",
        venture_name: "",
        founder_name: "",
        fund_name: "",
        fund_contact_email: "",
        why_contacted: "",
        data_sources: [],
        question_plan: [],
        structured: null,
        transcript: [],
      };
    }
  }

  async submitConsent(token: string, consent: ConsentPayload): Promise<void> {
    // Upstream convention: the FIRST chat message answers the consent prompt.
    await this.interviewRequest(`/${token}/message`, {
      method: "POST",
      body: JSON.stringify({ text: consent.agreed ? "I agree — continue." : "No, thank you." }),
    });
  }

  async submitStructuredAsks(_token: string, _asks: StructuredAsks): Promise<void> {
    // Uploads/structured asks are deferred upstream — collected client-side only.
  }

  async uploadInterviewFile(
    _token: string,
    kind: "cv" | "pitch",
    file: File,
  ): Promise<UploadedFileRef> {
    // Upstream defers uploads; keep the reference local so the UI flow works.
    return { kind, name: file.name, size_bytes: file.size, url: null };
  }

  async *streamInterviewMessage(
    token: string,
    text: string,
    signal?: AbortSignal,
  ): AsyncIterable<ChatStreamEvent> {
    let reply: { assistant: string; declined: boolean; done: boolean };
    try {
      reply = await this.interviewRequest(`/${token}/message`, {
        method: "POST",
        body: JSON.stringify({ text }),
        signal,
      });
    } catch (error) {
      yield { type: "error", message: (error as Error).message };
      return;
    }
    // Turn-based server — fake token streaming so the UI matches mock mode.
    const chunks = reply.assistant.split(/(?<=\s)/);
    for (const chunk of chunks) {
      if (signal?.aborted) return;
      await sleep(16);
      yield { type: "token", text: chunk };
    }
    yield { type: "done", messageId: reply.done ? "done" : "turn" };
  }

  async completeInterview(token: string): Promise<void> {
    await this.interviewRequest(`/${token}/complete`, { method: "POST" });
  }
}
