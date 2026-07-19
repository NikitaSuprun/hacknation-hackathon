/**
 * Scenario replay: every named beat must be reachable by replaying the same
 * mutations the UI performs, and must land on the exact demo-script state.
 */
import { afterEach, describe, expect, it } from "vitest";
import { INTERVIEW_SCRIPT } from "@/mocks/fixtures/chatScript";
import { GRASPLAB_ID } from "@/mocks/fixtures/seed";
import { SCENARIO_ORDER, applyScenario, currentScenarioGuess } from "@/mocks/scenarios";
import { getDB, resetDB } from "@/mocks/state";

afterEach(() => resetDB());

describe("applyScenario replay", () => {
  it("every scenario round-trips through currentScenarioGuess", () => {
    for (const id of SCENARIO_ORDER) {
      applyScenario(id);
      expect(currentScenarioGuess(), id).toBe(id);
    }
  });

  it("outreach-sent mints a sent row carrying the five-question plan", () => {
    applyScenario("outreach-sent");
    const db = getDB();
    const row = db.outreach.find((o) => o.venture_id === GRASPLAB_ID)!;
    expect(row.status).toBe("sent");
    expect(row.question_plan?.questions).toHaveLength(5);
    expect(db.ventures.find((v) => v.venture_id === GRASPLAB_ID)?.status).toBe("outreach");
  });

  it("consented records consent on the interview and the outreach row", () => {
    applyScenario("consented");
    const db = getDB();
    expect(db.interview.consented).toBe(true);
    expect(db.interview.stage).toBe("consented");
    expect(db.outreach.find((o) => o.venture_id === GRASPLAB_ID)?.status).toBe("consented");
  });

  it("candidacy-complete carries the structured asks from the demo script", () => {
    applyScenario("candidacy-complete");
    const structured = getDB().interview.structured!;
    expect(structured.linkedin_url).toBe("https://www.linkedin.com/in/lena-fischer-robotics");
    expect(structured.github_url).toBe("https://github.com/lenafischer");
    expect(structured.cv_file?.name).toBe("Lena_Fischer_CV.pdf");
    // Renders as "142 KB" / "2.1 MB" through FileDropzone's formatter.
    expect(Math.round(structured.cv_file!.size_bytes / 1024)).toBe(142);
    expect((structured.pitch_file!.size_bytes / (1024 * 1024)).toFixed(1)).toBe("2.1");
    expect(structured.traction_notes).toContain("41 companies");
  });

  it("interview-done replays the full 10-turn transcript and completes the interview", () => {
    applyScenario("interview-done");
    const db = getDB();
    expect(db.interview.stage).toBe("completed");

    const interviewer = db.interview.transcript.filter((m) => m.role === "interviewer");
    const founder = db.interview.transcript.filter((m) => m.role === "founder");
    expect(interviewer).toHaveLength(10);
    // The closing turn has no founder reply.
    expect(founder).toHaveLength(9);
    expect(interviewer[0]?.text).toBe(INTERVIEW_SCRIPT[0]?.ai);
    expect(interviewer[9]?.text).toBe(INTERVIEW_SCRIPT[9]?.ai);

    expect(db.outreach.find((o) => o.venture_id === GRASPLAB_ID)?.status).toBe("interviewed");
    expect(db.memos[GRASPLAB_ID]?.memo_id).toBe("memo-grasplab-post");
    expect(db.scoreHistory[GRASPLAB_ID]?.[0]?.score_id).toBe("score-post-interview");
  });

  it("replay is idempotent — re-applying a scenario rebuilds identical state", () => {
    applyScenario("interview-done");
    const first = JSON.stringify(getDB().ventures.find((v) => v.venture_id === GRASPLAB_ID));
    applyScenario("interview-done");
    const second = JSON.stringify(getDB().ventures.find((v) => v.venture_id === GRASPLAB_ID));
    // scored_at is stamped at mutation time; everything else must match.
    const strip = (s: string) => s.replace(/"scored_at":"[^"]+"/g, '"scored_at":"X"');
    expect(strip(second)).toBe(strip(first));
  });
});
