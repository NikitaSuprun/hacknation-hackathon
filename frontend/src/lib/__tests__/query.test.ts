import { describe, expect, it } from "vitest";
import type { CategoryKey, RankedVenture } from "@/lib/domain/types";
import {
  countActiveFilters,
  emptyQuery,
  isEmptyQuery,
  locationOf,
  locationOptionsOf,
  runQuery,
  sectorOptionsOf,
  type VentureQuery,
} from "@/lib/query";

// --- fixtures -------------------------------------------------------------

interface Stub {
  id: string;
  name: string;
  one_liner: string;
  tags: string[];
  score: number;
  status?: RankedVenture["status"];
  tier?: RankedVenture["quality_tier"];
  rationales?: Partial<Record<CategoryKey, string>>;
  claims?: string[];
}

function venture(s: Stub): RankedVenture {
  const categories: RankedVenture["breakdown"]["categories"] = {};
  for (const [key, rationale] of Object.entries(s.rationales ?? {})) {
    categories[key as CategoryKey] = {
      score: 70,
      method: "fixture",
      rationale,
      confidence: 0.8,
      evidence: [],
    };
  }
  if (s.claims?.length) {
    categories.problem_realness = {
      score: 70,
      method: "fixture",
      rationale: categories.problem_realness?.rationale ?? null,
      confidence: 0.8,
      evidence: s.claims.map((claim) => ({ claim, source_url: "https://example.com" })),
    };
  }
  return {
    venture_id: s.id,
    name: s.name,
    one_liner: s.one_liner,
    status: s.status ?? "scored",
    quality_tier: s.tier === undefined ? "scored" : s.tier,
    market_tags: s.tags,
    final_score: s.score,
    confidence: 0.8,
    ideal_match: null,
    s_individual_experience: null,
    s_schools: null,
    s_network_ties: null,
    s_prior_collaboration: null,
    s_problem_realness: null,
    s_product_defensibility: null,
    s_market: null,
    s_traction: null,
    breakdown: { schema_version: 1, categories },
    scored_at: "2026-07-15T09:00:00+00:00",
    funding_signal: null,
  };
}

const tactiSense = venture({
  id: "v-tacti",
  name: "TactiSense",
  one_liner: "Tactile skins that give warehouse robot arms a sense of touch.",
  tags: ["robotics", "hardware"],
  score: 74.2,
  rationales: {
    schools: "Founders met in the EPFL soft-robotics lab before spinning out.",
    problem_realness: "Fulfilment operators report grasping failures on deformable goods.",
  },
  claims: ["Pilot with a 3PL operator covering tactile sensing on pick-and-place cells"],
});

const graspLab = venture({
  id: "v-grasp",
  name: "GraspLab",
  one_liner: "Foundation models for robotic grasping",
  tags: ["robotics", "ai"],
  score: 71.5,
  status: "interviewing",
  rationales: {
    schools: "ETH spin-off; the founders are both ETH Zurich PhDs.",
    market: "Robotic manipulation TAM growing with named competitors.",
  },
});

const axonode = venture({
  id: "v-axon",
  name: "Axonode",
  one_liner: "Neuromorphic perception stacks for inspection drones.",
  tags: ["drones", "hardware", "ai"],
  score: 76.3,
  rationales: {
    schools: "Spun out of a UZH neuroinformatics group in Zurich.",
    product_defensibility: "Spiking vision pipeline runs onboard the UAV at 2W.",
  },
});

const voiceLab = venture({
  id: "v-voice",
  name: "VoiceLab",
  one_liner: "Multilingual voice agents for field technicians.",
  tags: ["ai", "voice"],
  score: 48.9,
  status: "sourced",
  tier: null,
  rationales: {
    traction: "Hackathon project out of KTH with early pilots in Stockholm.",
  },
});

const ceresbot = venture({
  id: "v-ceres",
  name: "Ceresbot",
  one_liner: "Autonomous weeding robots for row crops.",
  tags: ["agtech", "robotics"],
  score: 63.4,
  rationales: {
    market: "Swiss and German farms face herbicide restrictions; trials near Bern.",
  },
});

const POOL = [axonode, tactiSense, graspLab, ceresbot, voiceLab];

const q = (over: Partial<VentureQuery> = {}): VentureQuery => ({ ...emptyQuery(), ...over });
const ids = (hits: { venture: RankedVenture }[]) => hits.map((h) => h.venture.venture_id);

// --- query construction ---------------------------------------------------

describe("emptyQuery / isEmptyQuery", () => {
  it("round-trips", () => {
    expect(isEmptyQuery(emptyQuery())).toBe(true);
    expect(countActiveFilters(emptyQuery())).toBe(0);
  });

  it("detects each kind of constraint", () => {
    expect(isEmptyQuery(q({ text: "robots" }))).toBe(false);
    expect(isEmptyQuery(q({ text: "   " }))).toBe(true);
    expect(isEmptyQuery(q({ sectors: ["robotics"] }))).toBe(false);
    expect(isEmptyQuery(q({ locations: ["Zurich"] }))).toBe(false);
    expect(isEmptyQuery(q({ minScore: 60 }))).toBe(false);
    expect(isEmptyQuery(q({ statuses: ["sourced"] }))).toBe(false);
    expect(isEmptyQuery(q({ tiers: ["untiered"] }))).toBe(false);
  });

  it("counts free text as one filter", () => {
    expect(countActiveFilters(q({ text: "tactile", sectors: ["robotics", "ai"], minScore: 60 }))).toBe(4);
  });
});

// --- locationOf -----------------------------------------------------------

describe("locationOf", () => {
  it("infers Zurich from an ETH mention and marks it explicit when the city is named too", () => {
    const loc = locationOf(graspLab);
    expect(loc).toEqual({ city: "Zurich", confidence: "explicit" });
  });

  it("infers a city from an institution alone", () => {
    const epflOnly = venture({
      id: "v-epfl",
      name: "Périsurg",
      one_liner: "Steerable catheters for endovascular surgery.",
      tags: ["medtech"],
      score: 68,
      rationales: { schools: "Founded by EPFL microengineering alumni." },
    });
    expect(locationOf(epflOnly)).toEqual({ city: "Lausanne", confidence: "inferred" });
  });

  it("reads an explicit city mention with diacritics", () => {
    const geneva = venture({
      id: "v-gen",
      name: "Loopwise",
      one_liner: "SLAM for indoor logistics fleets.",
      tags: ["robotics"],
      score: 65,
      rationales: { market: "Pilot warehouses around Genève and Basel." },
    });
    expect(locationOf(geneva)?.city).toBe("Geneva");
    expect(locationOf(geneva)?.confidence).toBe("explicit");
  });

  it("prefers a forward-compatible location field when present", () => {
    const withField = { ...graspLab, location: "Zug" } as RankedVenture;
    expect(locationOf(withField)).toEqual({ city: "Zug", confidence: "explicit" });
    const withObject = {
      ...graspLab,
      location: { city: "Zürich", confidence: "inferred" },
    } as RankedVenture;
    expect(locationOf(withObject)).toEqual({ city: "Zurich", confidence: "inferred" });
  });

  it("returns null when nothing geographic is mentioned", () => {
    const nowhere = venture({
      id: "v-none",
      name: "Otterix",
      one_liner: "Developer tooling.",
      tags: ["devtools"],
      score: 40,
      rationales: { market: "No location signal in the corpus yet." },
    });
    expect(locationOf(nowhere)).toBeNull();
  });

  it("does not mistake substrings for institutions", () => {
    const decoy = venture({
      id: "v-decoy",
      name: "Method Labs",
      one_liner: "Ethernet fabric telemetry with a method-driven approach.",
      tags: ["infra"],
      score: 55,
      rationales: { market: "Ethernet switching methodology." },
    });
    expect(locationOf(decoy)).toBeNull();
  });
});

// --- option derivation ----------------------------------------------------

describe("option derivation", () => {
  it("unions market tags and derived cities", () => {
    expect(sectorOptionsOf(POOL)).toEqual(["agtech", "ai", "drones", "hardware", "robotics", "voice"]);
    expect(locationOptionsOf(POOL)).toEqual(["Bern", "Lausanne", "Stockholm", "Zurich"]);
  });
});

// --- structured filters ---------------------------------------------------

describe("structured filters", () => {
  it("keeps ranking order and null relevance when text is empty", () => {
    const hits = runQuery(POOL, emptyQuery());
    expect(ids(hits)).toEqual(["v-axon", "v-tacti", "v-grasp", "v-ceres", "v-voice"]);
    expect(hits.every((h) => h.relevance === null)).toBe(true);
    expect(hits.every((h) => h.matched.length === 0)).toBe(true);
  });

  it("intersects sector filters (OR across selected tags)", () => {
    expect(ids(runQuery(POOL, q({ sectors: ["agtech"] })))).toEqual(["v-ceres"]);
    expect(ids(runQuery(POOL, q({ sectors: ["agtech", "voice"] })))).toEqual(["v-ceres", "v-voice"]);
    expect(ids(runQuery(POOL, q({ sectors: ["ROBOTICS"] })))).toEqual(["v-tacti", "v-grasp", "v-ceres"]);
  });

  it("filters by derived location", () => {
    expect(ids(runQuery(POOL, q({ locations: ["Zurich"] })))).toEqual(["v-axon", "v-grasp"]);
    expect(ids(runQuery(POOL, q({ locations: ["Reykjavik"] })))).toEqual([]);
  });

  it("applies the minScore floor", () => {
    expect(ids(runQuery(POOL, q({ minScore: 70 })))).toEqual(["v-axon", "v-tacti", "v-grasp"]);
    expect(ids(runQuery(POOL, q({ minScore: 76.3 })))).toEqual(["v-axon"]);
  });

  it("filters by status and tier, treating null quality_tier as untiered", () => {
    expect(ids(runQuery(POOL, q({ statuses: ["interviewing"] })))).toEqual(["v-grasp"]);
    expect(ids(runQuery(POOL, q({ tiers: ["untiered"] })))).toEqual(["v-voice"]);
    expect(ids(runQuery(POOL, q({ tiers: ["scored"] })))).toHaveLength(4);
  });

  it("composes filters conjunctively across dimensions", () => {
    const hits = runQuery(POOL, q({ sectors: ["robotics"], locations: ["Zurich"], minScore: 70 }));
    expect(ids(hits)).toEqual(["v-grasp"]);
  });

  it("applies structured filters before scoring", () => {
    // TactiSense is the best text match but is excluded by the location filter.
    const hits = runQuery(POOL, q({ text: "tactile warehouse sensing", locations: ["Zurich"] }));
    expect(ids(hits)).not.toContain("v-tacti");
  });
});

// --- text scoring ---------------------------------------------------------

describe("semantic-ish text scoring", () => {
  it("ranks the tactile venture first with useful snippets", () => {
    const hits = runQuery(POOL, q({ text: "tactile warehouse sensing" }));
    expect(ids(hits)[0]).toBe("v-tacti");
    const top = hits[0];
    expect(top.relevance).toBeGreaterThan(0);
    expect(top.relevance).toBeLessThanOrEqual(1);
    expect(top.matched.length).toBeGreaterThan(0);
    expect(top.matched.length).toBeLessThanOrEqual(3);
    for (const m of top.matched) {
      expect(m.snippet.length).toBeLessThanOrEqual(90);
      expect(m.ranges.length).toBeGreaterThan(0);
      for (const [start, end] of m.ranges) {
        expect(start).toBeGreaterThanOrEqual(0);
        expect(end).toBeLessThanOrEqual(m.snippet.length);
        expect(end).toBeGreaterThan(start);
      }
    }
    expect(top.matched.some((m) => /tactile|warehouse|touch/i.test(m.snippet))).toBe(true);
  });

  it("finds the tactile venture through synonyms", () => {
    const hits = runQuery(POOL, q({ text: "robot arms touch sensing" }));
    expect(ids(hits)[0]).toBe("v-tacti");
    expect(hits[0].relevance).toBeGreaterThan(0);
  });

  it("matches drones via the UAV/aerial synonym group", () => {
    const hits = runQuery(POOL, q({ text: "UAV inspection" }));
    expect(ids(hits)[0]).toBe("v-axon");
  });

  it("matches agtech via the weeding/crop group", () => {
    const hits = runQuery(POOL, q({ text: "farming weed removal" }));
    expect(ids(hits)[0]).toBe("v-ceres");
  });

  it("is case- and plural-insensitive", () => {
    const a = runQuery(POOL, q({ text: "TACTILE SKINS" }));
    const b = runQuery(POOL, q({ text: "tactile skin" }));
    expect(ids(a)).toEqual(ids(b));
    expect(a[0].relevance).toBeCloseTo(b[0].relevance ?? 0, 5);
  });

  it("excludes zero-relevance ventures and normalizes to 0..1", () => {
    const hits = runQuery(POOL, q({ text: "endovascular catheter surgery" }));
    expect(hits).toHaveLength(0);
    for (const h of runQuery(POOL, q({ text: "robotics" }))) {
      expect(h.relevance).toBeGreaterThan(0);
      expect(h.relevance).toBeLessThanOrEqual(1);
    }
  });

  it("is deterministic and ties break on final_score", () => {
    const once = runQuery(POOL, q({ text: "robotics" }));
    const twice = runQuery(POOL, q({ text: "robotics" }));
    expect(ids(once)).toEqual(ids(twice));
    for (let i = 1; i < once.length; i++) {
      const prev = once[i - 1];
      const cur = once[i];
      if (prev.relevance === cur.relevance) {
        expect(prev.venture.final_score).toBeGreaterThanOrEqual(cur.venture.final_score);
      } else {
        expect(prev.relevance ?? 0).toBeGreaterThan(cur.relevance ?? 0);
      }
    }
  });

  it("rewards adjacent query terms (bigram bonus) over scattered ones", () => {
    const adjacent = runQuery(POOL, q({ text: "tactile skins" }))[0];
    expect(adjacent.venture.venture_id).toBe("v-tacti");
    expect(adjacent.relevance).toBeGreaterThan(0.3);
  });

  it("carries the derived city on every hit", () => {
    const hits = runQuery(POOL, q({ text: "grasping" }));
    expect(hits.find((h) => h.venture.venture_id === "v-grasp")?.city).toBe("Zurich");
  });

  it("scores the full demo prompt with TactiSense on top", () => {
    const hits = runQuery(POOL, q({ text: "tactile sensing for warehouse robot arms in Zurich" }));
    expect(ids(hits)[0]).toBe("v-tacti");
    expect(hits.length).toBeGreaterThan(1);
  });
});
