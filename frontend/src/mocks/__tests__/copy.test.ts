/**
 * Copy audit: the founder-facing voice never uses the language of an
 * application process ("You don't apply. You get chosen."). The interview
 * script is the founder-facing surface, every AI turn must stay clean.
 */
import { describe, expect, it } from "vitest";
import { FOLLOW_UP_REPLY, INTERVIEW_SCRIPT } from "@/mocks/fixtures/chatScript";
import {
  AXONODE_MEMO_SECTIONS,
  GRASPLAB_MEMO_POST_SECTIONS,
  GRASPLAB_MEMO_PRE_SECTIONS,
  TACTISENSE_MEMO_SECTIONS,
} from "@/mocks/fixtures/memos";
import { EXTRA_VENTURES } from "@/mocks/fixtures/extraVentures";
import { DEMO_STEPS } from "@/demo/script";

const BANNED =
  /\b(apply|applies|applying|applied|application|applications|submit|submits|submitted|submitting|submission|submissions)\b/i;

/** The brand writes without em or en dashes; hyphens are fine. (Unicode escapes so copy sweeps can't rewrite this regex.) */
const DASHES = /[–—]/;

const CLOSING = INTERVIEW_SCRIPT.length - 1;

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

  it("warm, consent-first shape: 8 AI turns, no exclamation marks, closing turn ends the chat", () => {
    expect(INTERVIEW_SCRIPT).toHaveLength(8);
    for (const turn of INTERVIEW_SCRIPT) {
      expect(turn.ai).not.toContain("!");
    }
    expect(INTERVIEW_SCRIPT[0]?.ai).toContain("consent");
    expect(INTERVIEW_SCRIPT[CLOSING]?.founder).toBeNull();
    expect(INTERVIEW_SCRIPT[CLOSING]?.ai).toContain("never a promise of investment");
  });

  it("no em or en dashes in any user-visible fixture or caption", () => {
    for (const turn of INTERVIEW_SCRIPT) {
      expect(turn.ai).not.toMatch(DASHES);
      if (turn.founder) expect(turn.founder).not.toMatch(DASHES);
    }
    expect(FOLLOW_UP_REPLY).not.toMatch(DASHES);
    for (const sections of [
      GRASPLAB_MEMO_PRE_SECTIONS,
      GRASPLAB_MEMO_POST_SECTIONS,
      AXONODE_MEMO_SECTIONS,
      TACTISENSE_MEMO_SECTIONS,
    ]) {
      expect(JSON.stringify(sections)).not.toMatch(DASHES);
    }
    for (const venture of EXTRA_VENTURES) {
      expect(JSON.stringify(venture.breakdown)).not.toMatch(DASHES);
      expect(venture.one_liner).not.toMatch(DASHES);
    }
    for (const step of DEMO_STEPS) {
      if (step.caption) expect(step.caption).not.toMatch(DASHES);
    }
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
