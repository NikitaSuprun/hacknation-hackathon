/**
 * Contract validation for the authored demo dataset: every venture row,
 * memo, gap, and team member must satisfy the zod mirrors of the schemas
 * the live backend enforces.
 */
import { describe, expect, it } from "vitest";
import {
  memoSchema,
  memoSectionsSchema,
  rankedVentureSchema,
  ventureGapSchema,
  ventureTeamMemberSchema,
} from "@/lib/domain/schemas";
import {
  EXTRA_GAPS,
  EXTRA_MEMOS,
  EXTRA_TEAM,
  EXTRA_VENTURES,
} from "@/mocks/fixtures/extraVentures";
import {
  GRASPLAB_MEMO_POST_SECTIONS,
  GRASPLAB_MEMO_PRE_SECTIONS,
} from "@/mocks/fixtures/memos";
import { GRASPLAB_ID, seedDB } from "@/mocks/fixtures/seed";

function expectValid<T>(
  result: { success: boolean; error?: { issues: unknown } },
  label: string,
): void {
  expect(result.success, `${label}: ${JSON.stringify(result.error?.issues ?? [])}`).toBe(true);
}

describe("extra ventures", () => {
  it("every EXTRA_VENTURES row validates against rankedVentureSchema", () => {
    expect(EXTRA_VENTURES).toHaveLength(9);
    for (const venture of EXTRA_VENTURES) {
      expectValid(rankedVentureSchema.safeParse(venture), venture.name);
    }
  });

  it("every assembled seed venture (GraspLab, VoiceLab, extras) validates", () => {
    const seed = seedDB();
    // 2 generated fixtures + 9 authored extras
    expect(seed.ventures).toHaveLength(11);
    for (const venture of seed.ventures) {
      expectValid(rankedVentureSchema.safeParse(venture), venture.name);
    }
  });

  it("every team member validates and belongs to its venture", () => {
    for (const [ventureId, members] of Object.entries(EXTRA_TEAM)) {
      expect(members.length).toBeGreaterThanOrEqual(1);
      expect(members.length).toBeLessThanOrEqual(3);
      for (const m of members) {
        expectValid(ventureTeamMemberSchema.safeParse(m), m.full_name);
        expect(m.venture_id).toBe(ventureId);
      }
    }
  });

  it("reuses the fixture persons for Aisha Patel (Loopwise) and Nils Berger (FastSim)", () => {
    const loopwise = EXTRA_TEAM["cccc0008-0000-4000-8000-000000000008"] ?? [];
    expect(loopwise.map((m) => m.person_id)).toContain("55555555-5555-4555-8555-000000000005");
    const fastsim = EXTRA_TEAM["cccc0003-0000-4000-8000-000000000003"] ?? [];
    expect(fastsim.map((m) => m.person_id)).toContain("44444444-4444-4444-8444-000000000004");
  });
});

describe("memos", () => {
  it("GraspLab pre/post sections conform to memo.schema (all 9 sections, 2-4 bullets)", () => {
    for (const [label, sections] of [
      ["pre", GRASPLAB_MEMO_PRE_SECTIONS],
      ["post", GRASPLAB_MEMO_POST_SECTIONS],
    ] as const) {
      expectValid(memoSectionsSchema.safeParse(sections), `grasplab-${label}`);
      for (const [key, section] of Object.entries(sections)) {
        if (key === "schema_version") continue;
        const bullets = (section as { bullets: unknown[] }).bullets;
        expect(bullets.length, `grasplab-${label}.${key}`).toBeGreaterThanOrEqual(2);
        expect(bullets.length, `grasplab-${label}.${key}`).toBeLessThanOrEqual(4);
      }
    }
  });

  it("PRE memo leaves TAM/SAM/SOM open with a market.tam gap; POST fills all three", () => {
    const pre = GRASPLAB_MEMO_PRE_SECTIONS.market_tam_sam_som;
    expect(pre.tam).toBeNull();
    expect(pre.sam).toBeNull();
    expect(pre.som).toBeNull();
    expect(pre.bullets.some((b) => b.missing && b.gap_field === "market.tam")).toBe(true);

    const post = GRASPLAB_MEMO_POST_SECTIONS.market_tam_sam_som;
    expect(post.tam).toContain("CHF 2.1B");
    expect(post.sam).toContain("CHF 480M");
    expect(post.som).toContain("CHF 115M");
    expect(post.bullets.every((b) => !b.missing)).toBe(true);
  });

  it("POST memo cites the interview for every filled gap", () => {
    const interviewEvidence = JSON.stringify(GRASPLAB_MEMO_POST_SECTIONS);
    expect(interviewEvidence).toContain("app://interview/bbbbbbbb-0000-4000-8000-000000000005");
    // No missing bullets survive the interview.
    for (const section of Object.values(GRASPLAB_MEMO_POST_SECTIONS)) {
      if (typeof section === "number") continue;
      for (const bullet of (section as { bullets: { missing?: boolean }[] }).bullets) {
        expect(bullet.missing ?? false).toBe(false);
      }
    }
  });

  it("all served memos (seed + post) validate against the memo schema", () => {
    const seed = seedDB();
    for (const memo of [...Object.values(seed.memos), ...Object.values(seed.postMemos)]) {
      expectValid(memoSchema.safeParse(memo), memo.memo_id);
    }
  });

  it("only GraspLab, Axonode, and TactiSense have memos — the rest use the no-memo state", () => {
    const seed = seedDB();
    expect(Object.keys(seed.memos).sort()).toEqual(
      [
        GRASPLAB_ID,
        "cccc0001-0000-4000-8000-000000000001",
        "cccc0002-0000-4000-8000-000000000002",
      ].sort(),
    );
    expect(Object.keys(EXTRA_MEMOS)).toHaveLength(2);
  });
});

describe("gaps", () => {
  it("every gap row validates against ventureGapSchema", () => {
    const seed = seedDB();
    for (const gaps of Object.values(seed.gaps)) {
      for (const gap of gaps) expectValid(ventureGapSchema.safeParse(gap), gap.field);
    }
  });

  it("the authored GraspLab gaps replace the generated ones (all 5, importance-ordered)", () => {
    const seed = seedDB();
    expect(seed.gaps[GRASPLAB_ID]).toEqual(EXTRA_GAPS[GRASPLAB_ID]);
    expect(seed.gaps[GRASPLAB_ID]?.map((g) => g.field)).toEqual([
      "traction.revenue",
      "market.tam",
      "team.commitment",
      "tech.ip_licensing",
      "funding.history_verified",
    ]);
    expect(seed.gaps[GRASPLAB_ID]?.map((g) => g.importance)).toEqual([0.9, 0.7, 0.62, 0.55, 0.5]);
  });

  it("the sent-outreach question plan carries the five gap questions", async () => {
    const { buildSentOutreachRow } = await import("@/mocks/fixtures/seed");
    const row = buildSentOutreachRow();
    expect(row.question_plan?.questions).toHaveLength(5);
    expect(row.question_plan?.questions[0]).toBe("Do you have paying pilots or revenue today?");
  });
});
