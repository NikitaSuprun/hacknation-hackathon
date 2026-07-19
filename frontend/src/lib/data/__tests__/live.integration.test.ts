/**
 * Live integration suite: LiveDataSource end-to-end against the in-repo
 * fixtures server. Skipped unless LIVE_URL is set.
 *
 * From the repo root:
 *   uv run python -m app serve --fixtures --port 8799   (background)
 *   cd frontend && LIVE_URL=http://127.0.0.1:8799 npm run test -- live.integration
 *
 * The suite drives the full demo loop: login -> thesis/weights -> ranking ->
 * memo/scores/team -> outreach (mints a real interview token) -> consent ->
 * two chat turns (answer + skip) -> complete -> rescore -> outreach board.
 * Fixtures state is in-memory server-side; restart the server for a pristine
 * run (in particular, opting the founder out suppresses future outreach).
 */
import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";
import { LiveDataSource } from "@/lib/data/LiveDataSource";
import { login, logout } from "@/lib/auth";
import { MEMO_SECTION_KEYS } from "@/lib/domain/types";
import type { OutreachRow, RankedVenture } from "@/lib/domain/types";

// tsconfig types are restricted to vite/client; declare the Node global we use.
declare const process: { env: Record<string, string | undefined> };

const LIVE_URL = process.env.LIVE_URL ?? "";
const LIVE_PASSWORD = process.env.LIVE_PASSWORD ?? "demo";

/** vitest runs in the node environment — Web Storage does not exist there. */
class MemoryStorage implements Storage {
  private store = new Map<string, string>();
  get length(): number {
    return this.store.size;
  }
  clear(): void {
    this.store.clear();
  }
  getItem(key: string): string | null {
    return this.store.get(key) ?? null;
  }
  key(index: number): string | null {
    return Array.from(this.store.keys())[index] ?? null;
  }
  removeItem(key: string): void {
    this.store.delete(key);
  }
  setItem(key: string, value: string): void {
    this.store.set(key, String(value));
  }
}

/**
 * Node 22 exposes localStorage as an experimental getter that yields undefined
 * without --localstorage-file — plain assignment can be a no-op, so install
 * the shim with defineProperty when the global is not a usable Storage.
 */
function installStorage(name: "localStorage" | "sessionStorage"): void {
  const existing = (globalThis as Record<string, unknown>)[name];
  if (existing && typeof (existing as Storage).getItem === "function") return;
  Object.defineProperty(globalThis, name, {
    value: new MemoryStorage(),
    configurable: true,
    writable: true,
  });
}
installStorage("localStorage");
installStorage("sessionStorage");

async function collectAssistantText(
  source: LiveDataSource,
  token: string,
  text: string,
): Promise<{ text: string; last: string }> {
  let collected = "";
  let last = "";
  for await (const event of source.streamInterviewMessage(token, text)) {
    if (event.type === "token") collected += event.text;
    if (event.type === "done") last = event.messageId;
    if (event.type === "error") throw new Error(event.message);
  }
  return { text: collected, last };
}

describe.skipIf(!LIVE_URL)("LiveDataSource against the fixtures server", () => {
  const source = new LiveDataSource();
  let thesisId = "";
  let grasplab: RankedVenture | undefined;
  let outreach: OutreachRow | undefined;
  let interviewToken = "";

  beforeAll(async () => {
    // apiBase() reads VITE_API_BASE lazily, so stubbing here is early enough.
    vi.stubEnv("VITE_API_BASE", LIVE_URL);
    await login(LIVE_PASSWORD);
  });

  afterAll(() => {
    logout();
    vi.unstubAllEnvs();
  });

  it("lists theses from the envelope", async () => {
    const theses = await source.listTheses();
    expect(theses.length).toBeGreaterThan(0);
    thesisId = theses[0].thesis_id;
    expect(thesisId).toBeTruthy();
  });

  it("returns the active weights row with all nine categories", async () => {
    const weights = await source.getWeights(thesisId);
    for (const key of [
      "w_individual_experience",
      "w_schools",
      "w_network_ties",
      "w_prior_collaboration",
      "w_problem_realness",
      "w_product_defensibility",
      "w_market",
      "w_traction",
      "w_ideal_match",
    ] as const) {
      expect(weights[key]).toBeTypeOf("number");
    }
  });

  it("ranks the pool with GraspLab present and breakdown parsed", async () => {
    const ranking = await source.getRanking(thesisId);
    expect(ranking.length).toBeGreaterThan(0);
    grasplab = ranking.find((v) => v.name === "GraspLab");
    expect(grasplab).toBeDefined();
    expect(typeof grasplab!.breakdown).toBe("object");
    expect(grasplab!.breakdown.categories).toBeTypeOf("object");
    expect(
      Object.keys(grasplab!.breakdown.categories).length,
    ).toBeGreaterThan(0);
    expect(grasplab!.final_score).toBeGreaterThan(0);
  });

  it("returns the memo with all nine sections parsed", async () => {
    const memo = await source.getVentureMemo(grasplab!.venture_id);
    expect(memo.venture_id).toBe(grasplab!.venture_id);
    expect(memo.thesis_id).toBeTruthy();
    for (const key of MEMO_SECTION_KEYS) {
      expect(memo.sections[key]).toBeDefined();
      expect(Array.isArray(memo.sections[key].bullets)).toBe(true);
    }
  });

  it("returns score history newest-first with parsed breakdowns", async () => {
    const scores = await source.getVentureScores(grasplab!.venture_id);
    expect(scores.length).toBeGreaterThan(0);
    for (const snapshot of scores) {
      expect(typeof snapshot.breakdown).toBe("object");
    }
    const stamps = scores.map((s) => s.scored_at);
    expect([...stamps].sort().reverse()).toEqual(stamps);
  });

  it("returns the team with evidence parsed", async () => {
    const team = await source.getVentureTeam(grasplab!.venture_id);
    expect(team.length).toBeGreaterThan(0);
    for (const member of team) {
      expect(member.full_name).toBeTruthy();
      if (member.evidence !== null) expect(typeof member.evidence).toBe("object");
    }
  });

  it("sends outreach and returns the minted interview_url", async () => {
    outreach = await source.sendOutreach(grasplab!.venture_id, {
      to_email: "",
      subject: "",
      body: "",
    });
    expect(outreach.status).toBe("sent");
    expect(outreach.interview_url).toContain("/interview/");
    expect(outreach.to_email).toContain("@");
    interviewToken = outreach.interview_url!.split("/interview/")[1];
    expect(interviewToken).toMatch(/^[0-9a-f]{32}$/);
  });

  it("opens the interview at pending_consent", async () => {
    const session = await source.getInterviewSession(interviewToken);
    expect(session.stage).toBe("pending_consent");
    expect(session.venture_name).toBe("GraspLab");
    expect(session.consent_prompt).toContain("consent");
    expect(session.transcript).toEqual([]);
  });

  it("records consent through the first chat turn", async () => {
    await source.submitConsent(interviewToken, {
      agreed: true,
      consent_text: "I agree — continue.",
    });
    const session = await source.getInterviewSession(interviewToken);
    expect(session.stage).toBe("in_progress");
    expect(session.transcript.length).toBeGreaterThan(0);
    expect(session.transcript[0].role).toBe("interviewer");
  });

  it("streams two chat turns (answer, then skip)", async () => {
    const first = await collectAssistantText(
      source,
      interviewToken,
      "We have 3 pilot customers and a working demo.",
    );
    expect(first.text.length).toBeGreaterThan(0);
    const second = await collectAssistantText(source, interviewToken, "skip");
    expect(second.text.length).toBeGreaterThan(0);
    expect(second.text).toContain("skip");
  });

  it("completes the interview", { timeout: 20000 }, async () => {
    await expect(source.completeInterview(interviewToken)).resolves.toBeUndefined();
  });

  it("marks the consumed link as completed on re-open", async () => {
    const session = await source.getInterviewSession(interviewToken);
    expect(session.stage).toBe("completed");
  });

  it("rescores the venture now that an interview completed", async () => {
    const handle = await source.rescoreVenture(grasplab!.venture_id);
    expect(handle.runId).toBeTruthy();
    await expect(source.getRunStatus(handle)).resolves.toBe("succeeded");
  });

  it("shows the outreach as interviewed on the board", async () => {
    const rows = await source.listOutreach(thesisId);
    const row = rows.find((r) => r.outreach_id === outreach!.outreach_id);
    expect(row).toBeDefined();
    expect(row!.status).toBe("interviewed");
    expect(Array.isArray(row!.history)).toBe(true);
    expect(row!.question_plan?.questions.length).toBeGreaterThan(0);
  });
});
