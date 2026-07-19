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
import { apiBase, clearSessionToken, getSessionToken } from "@/lib/auth";
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
  ScoreSnapshot,
  ScoreWeights,
  StructuredAsks,
  Thesis,
  ThesisInput,
  UploadedFileRef,
  VentureGap,
  VentureTeamMember,
} from "@/lib/domain/types";

/**
 * VARIANT columns arrive as JSON strings from the Statement Execution API.
 * (Some payloads — interview transcript, outreach history — arrive as native
 * JSON already; both shapes are accepted.)
 */
function parseVariant<T>(value: unknown): T | null {
  if (value == null) return null;
  return (typeof value === "string" ? JSON.parse(value) : value) as T;
}

/**
 * The server's error surface: {"error": "..."} everywhere except the
 * ideal-candidate validator, which returns {"errors": ["...", ...]} on 422.
 */
function errorMessage(body: unknown): string | null {
  if (body === null || typeof body !== "object") return null;
  const { error, errors } = body as { error?: unknown; errors?: unknown };
  if (typeof error === "string" && error) return error;
  if (Array.isArray(errors)) {
    const messages = errors.filter((item): item is string => typeof item === "string");
    if (messages.length > 0) return messages.join("; ");
  }
  return null;
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
    const response = await fetch(`${apiBase()}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(init?.headers ?? {}),
      },
    });
    if (response.status === 401) {
      // Sessions are in-memory server-side: {"error":"unauthorized"} after a
      // restart (or a bad password on /v1/login). Either way, re-login.
      clearSessionToken();
      throw new Error("Session expired — sign in again.");
    }
    if (!response.ok) {
      const body: unknown = await response.json().catch(() => null);
      throw new Error(errorMessage(body) ?? `${path} failed (${response.status})`);
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

  async saveThesis(input: ThesisInput): Promise<Thesis> {
    // The upsert echoes the stored row; it sets updated_at but (verified) not
    // updated_by, so default it rather than surface undefined.
    const row = await this.request<Record<string, unknown>>("/v1/thesis", {
      method: "POST",
      body: JSON.stringify(input),
    });
    return { updated_by: "app", ...row } as unknown as Thesis;
  }

  async getWeights(thesisId: string): Promise<ScoreWeights> {
    const { weights } = await this.thesisEnvelope();
    // Server-side "active" is `is_active is not False` — mirror that here.
    const row =
      weights.find((w) => w.thesis_id === thesisId && w.is_active !== false) ?? weights[0];
    if (!row) throw new Error("No weights configured for this thesis.");
    return row;
  }

  async saveWeights(thesisId: string, weights: ScoreWeights): Promise<void> {
    // Verified: the server reads exactly the nine w_* keys and tolerates the
    // rest of the row (bookkeeping fields in the body are ignored) — 422 with
    // {"error": "missing or non-numeric weights: ..."} only when one is absent.
    await this.request(`/v1/thesis/${thesisId}/weights`, {
      method: "PUT",
      body: JSON.stringify(weights),
    });
  }

  async getIdealCandidate(thesisId: string): Promise<IdealCandidateProfile> {
    const { ideals } = await this.thesisEnvelope();
    const row =
      ideals.find((r) => r.thesis_id === thesisId && r.is_active !== false) ?? ideals[0];
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
    return ventures.map((row) => {
      // Verified: breakdown is null for pool ventures without a score row —
      // degrade to an empty breakdown instead of failing the whole ranking.
      const breakdown = parseVariant(row.breakdown);
      return {
        ...(row as unknown as RankedVenture),
        // Verified present on the wire (from gold.venture), but nullable.
        quality_tier: (row.quality_tier as RankedVenture["quality_tier"]) ?? null,
        market_tags: parseVariant<string[]>(row.market_tags) ?? [],
        breakdown: breakdown
          ? (scoreBreakdownSchema.parse(breakdown) as unknown as ScoreBreakdown)
          : { schema_version: 1, categories: {} },
        // Verified absent from /v1/ranking (it lives on gold.candidate_pool) —
        // null keeps the badge hidden.
        funding_signal: (row.funding_signal as RankedVenture["funding_signal"]) ?? null,
      };
    });
  }

  async getVentureScores(ventureId: string): Promise<ScoreSnapshot[]> {
    const { scores } = await this.request<{ scores: Record<string, unknown>[] }>(
      `/v1/venture/${ventureId}/scores`,
    );
    return scores.map((row) => ({
      ...(row as unknown as ScoreSnapshot),
      breakdown: scoreBreakdownSchema.parse(
        parseVariant(row.breakdown),
      ) as unknown as ScoreBreakdown,
    }));
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
    if (!row) {
      // The row should always be listable right after the POST; synthesize a
      // board-renderable stub from the POST result if it somehow is not.
      return {
        outreach_id: result.outreach_id,
        venture_id: ventureId,
        person_id: "",
        thesis_id: "",
        channel: "email",
        to_email: result.to_email,
        subject: "",
        body: "",
        interview_url: result.interview_url,
        status: result.status,
        sent_at: null,
        consent_at: null,
        last_event_at: null,
        token_expires_at: null,
        question_plan: null,
        history: null,
        created_by: "app",
        updated_at: new Date().toISOString(),
      };
    }
    return {
      ...(row as unknown as OutreachRow),
      question_plan: parseVariant<{ questions: string[] }>(row.question_plan),
      history: parseVariant<unknown[]>(row.history),
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
    const response = await fetch(`${apiBase()}/v1/interview${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        "X-Interview-Session": interviewSessionId(),
        ...(init?.headers ?? {}),
      },
    });
    if (!response.ok) {
      // Verified statuses: 400 missing session header, 404 unknown token,
      // 409 token bound to another device, 410 expired/consumed link,
      // 403 complete-before-consent, 422 empty text / invalid extraction.
      const body: unknown = await response.json().catch(() => null);
      const error = new Error(
        errorMessage(body) ?? `Interview request failed (${response.status})`,
      );
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
      const { status, message } = error as Error & { status?: number };
      // 410 covers both "link has expired" and "no longer usable (status: X)";
      // an interviewed link means the founder already finished — show that.
      const stage =
        status === 410
          ? message.includes("status: interviewed")
            ? "completed"
            : "expired"
          : "invalid"; // 404 unknown token, 409 open on another device
      return {
        token,
        stage,
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
