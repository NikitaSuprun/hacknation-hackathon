/**
 * Copy audit: CHOSEN's founder-facing voice never uses the language of an
 * application process ("You don't apply. You get chosen."). The interview
 * script is the founder-facing surface — every AI turn must stay clean.
 */
import { describe, expect, it } from "vitest";
import { INTERVIEW_SCRIPT } from "@/mocks/fixtures/chatScript";

const BANNED =
  /\b(apply|applies|applying|applied|application|applications|submit|submits|submitted|submitting|submission|submissions)\b/i;

describe("interview script copy", () => {
  it("no banned application-process words in any AI turn", () => {
    for (const turn of INTERVIEW_SCRIPT) {
      expect(turn.ai).not.toMatch(BANNED);
    }
  });

  it("founder replies stay clean too", () => {
    for (const turn of INTERVIEW_SCRIPT) {
      if (turn.founder) expect(turn.founder).not.toMatch(BANNED);
    }
  });

  it("warm, consent-first shape: 10 AI turns, no exclamation marks, closing turn ends the chat", () => {
    expect(INTERVIEW_SCRIPT).toHaveLength(10);
    for (const turn of INTERVIEW_SCRIPT) {
      expect(turn.ai).not.toContain("!");
    }
    expect(INTERVIEW_SCRIPT[0]?.ai).toContain("consent");
    expect(INTERVIEW_SCRIPT[9]?.founder).toBeNull();
    expect(INTERVIEW_SCRIPT[9]?.ai).toContain("never a promise of investment");
  });

  it("the five gap fills appear in interview order", () => {
    const fills = INTERVIEW_SCRIPT.flatMap((turn) => turn.fills ?? []);
    expect(fills).toEqual([
      "traction.revenue",
      "market.tam",
      "team.commitment",
      "tech.ip_licensing",
      "funding.history_verified",
    ]);
  });
});
