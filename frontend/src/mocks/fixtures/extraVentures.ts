/**
 * The 9 hand-authored ventures that join GraspLab in the ranked list, plus
 * their teams, the GraspLab gap plan (replaces the generated fixture gaps),
 * and full memos for the two runners-up (Axonode, TactiSense). Other extras
 * intentionally have no memo — the UI shows its branded "no memo yet" state.
 *
 * All companies, people, outlets, and URLs are fictional. Category scores
 * satisfy rerank.computeFinalScore arithmetic exactly (the client recomputes
 * finals live); a vitest suite pins every final to the value stored here.
 */
import {
  CATEGORY_KEYS,
  type CategoryKey,
  type Evidence,
  type Memo,
  type RankedVenture,
  type ScoreBreakdown,
  type VentureGap,
  type VentureTeamMember,
} from "@/lib/domain/types";
import { AXONODE_MEMO_SECTIONS, TACTISENSE_MEMO_SECTIONS } from "./memos";

/** Same value as seed.GRASPLAB_ID — duplicated locally to avoid a cyclic import. */
const GRASPLAB = "81963541-592e-5edf-8b82-9fe0b26b4555";
const THESIS_ID = "aaaaaaaa-0000-4000-8000-000000000001";

// --- Deterministic venture ids ---
export const AXONODE_ID = "cccc0001-0000-4000-8000-000000000001";
export const TACTISENSE_ID = "cccc0002-0000-4000-8000-000000000002";
export const FASTSIM_ID = "cccc0003-0000-4000-8000-000000000003";
export const WAYLINE_ID = "cccc0004-0000-4000-8000-000000000004";
export const CERESBOT_ID = "cccc0005-0000-4000-8000-000000000005";
export const PERISURG_ID = "cccc0006-0000-4000-8000-000000000006";
export const CAIRNSIGHT_ID = "cccc0007-0000-4000-8000-000000000007";
export const LOOPWISE_ID = "cccc0008-0000-4000-8000-000000000008";
export const OTTERIX_ID = "cccc0009-0000-4000-8000-000000000009";

/** Fixture persons reused (ground truth in generated.ts). */
const AISHA_PATEL_PERSON_ID = "55555555-5555-4555-8555-000000000005";
const NILS_BERGER_PERSON_ID = "44444444-4444-4444-8444-000000000004";

const METHODS: Record<CategoryKey, string> = {
  individual_experience: "sql_features",
  schools: "deterministic",
  network_ties: "graph",
  prior_collaboration: "sql_overlap",
  problem_realness: "web_agent",
  product_defensibility: "ai_query",
  market: "web_agent",
  traction: "hybrid",
  ideal_match: "structured_match",
};

const ev = (claim: string, source_url: string, source_type: string): Evidence => ({
  claim,
  source_url,
  source_type,
});

interface CategoryInput {
  score: number | null;
  rationale: string;
  confidence: number;
  evidence: Evidence[];
}

interface VentureSpec {
  venture_id: string;
  name: string;
  one_liner: string;
  status: RankedVenture["status"];
  quality_tier: RankedVenture["quality_tier"];
  market_tags: string[];
  /** Must equal computeFinalScore over the categories under default weights. */
  final_score: number;
  confidence: number;
  funding_signal: RankedVenture["funding_signal"];
  scored_at: string;
  categories: Record<CategoryKey, CategoryInput>;
}

function buildVenture(spec: VentureSpec): RankedVenture {
  const breakdown: ScoreBreakdown = { schema_version: 1, categories: {} };
  for (const key of CATEGORY_KEYS) {
    const c = spec.categories[key];
    breakdown.categories[key] = {
      score: c.score,
      method: METHODS[key],
      rationale: c.rationale,
      confidence: c.confidence,
      evidence: c.evidence,
    };
  }
  const c = spec.categories;
  return {
    venture_id: spec.venture_id,
    name: spec.name,
    one_liner: spec.one_liner,
    status: spec.status,
    quality_tier: spec.quality_tier,
    market_tags: spec.market_tags,
    final_score: spec.final_score,
    confidence: spec.confidence,
    ideal_match: c.ideal_match.score,
    s_individual_experience: c.individual_experience.score,
    s_schools: c.schools.score,
    s_network_ties: c.network_ties.score,
    s_prior_collaboration: c.prior_collaboration.score,
    s_problem_realness: c.problem_realness.score,
    s_product_defensibility: c.product_defensibility.score,
    s_market: c.market.score,
    s_traction: c.traction.score,
    breakdown,
    scored_at: spec.scored_at,
    funding_signal: spec.funding_signal,
  };
}

// ---------------------------------------------------------------------------
// Ventures
// ---------------------------------------------------------------------------

const AX_REPO = "https://github.com/axonode-ai/spikeflow";
const AX_PAPER = "https://arxiv.org/abs/2602.10771";
const AX_ZEFIX = "https://www.zefix.admin.ch/api/v1/company/uid/CHE-214.882.331";
const AX_PRESS = "https://www.roboticsweekly.eu/2026/06/axonode-neuromorphic-drones";
const AX_OPENALEX = "https://api.openalex.org/works/W4409120344";

const axonode = buildVenture({
  venture_id: AXONODE_ID,
  name: "Axonode",
  one_liner: "Neuromorphic edge inference for autonomous drones",
  status: "scored",
  quality_tier: "scored",
  market_tags: ["ai", "robotics", "semiconductors"],
  final_score: 76.3,
  confidence: 0.74,
  funding_signal: "none_found",
  scored_at: "2026-07-14T08:30:00+00:00",
  categories: {
    individual_experience: {
      score: 88,
      confidence: 0.8,
      rationale:
        "Ricci first-authored three neuromorphic-inference papers and is primary maintainer of the 2,900-star spikeflow runtime. Lindqvist shipped flight-controller firmware in two drone programs.",
      evidence: [
        ev("Three first-author papers on event-driven inference, 2024–2026.", AX_OPENALEX, "openalex"),
        ev("Ricci is top committer on spikeflow (2,900 stars).", AX_REPO, "github"),
      ],
    },
    schools: {
      score: 90,
      confidence: 0.85,
      rationale:
        "EPFL postdoc plus a KTH embedded-systems MSc — both top-tier engineering programs on record.",
      evidence: [ev("Affiliations: EPFL (Ricci), KTH (Lindqvist).", AX_OPENALEX, "openalex")],
    },
    network_ties: {
      score: 75,
      confidence: 0.7,
      rationale: "One-hop coauthor paths to two funded robotics founders in the EPFL spin-off cluster.",
      evidence: [ev("Coauthor graph reaches two funded founders at distance 1.", AX_OPENALEX, "openalex")],
    },
    prior_collaboration: {
      score: 30,
      confidence: 0.75,
      rationale:
        "Ricci and Lindqvist first co-committed three months ago; no shared papers or repositories before April 2026.",
      evidence: [ev("First co-commit on spikeflow dated 2026-04-08.", AX_REPO, "github")],
    },
    problem_realness: {
      score: 78,
      confidence: 0.7,
      rationale:
        "Drone OEMs report that cloud round-trips break autonomy beyond line of sight; sub-5W on-board inference is a recurring, documented ask.",
      evidence: [ev("OEMs cite connectivity limits for BVLOS autonomy.", AX_PRESS, "press")],
    },
    product_defensibility: {
      score: 74,
      confidence: 0.65,
      rationale:
        "Compiler co-designed with off-the-shelf neuromorphic silicon; scheduling kernels closed while the runtime API is open. Dependence on third-party chip roadmaps caps the score.",
      evidence: [
        ev("Open runtime, closed scheduler split documented in v0.9 notes.", AX_REPO, "github"),
        ev("~10x energy reduction vs GPU baseline in published benchmark.", AX_PAPER, "arxiv"),
      ],
    },
    market: {
      score: 85,
      confidence: 0.7,
      rationale:
        "Edge-AI for uncrewed systems grows across inspection, delivery, and agriculture; European autonomy programs fund on-board compute.",
      evidence: [ev("Edge autonomy spend forecast, June 2026.", AX_PRESS, "press")],
    },
    traction: {
      score: 86,
      confidence: 0.75,
      rationale:
        "2,900 stars within four months of release plus two paid evaluation agreements with European drone OEMs referenced in a June press note.",
      evidence: [
        ev("2,900 stars, 41 contributors on spikeflow.", AX_REPO, "github"),
        ev("Two paid OEM evaluations announced.", AX_PRESS, "press"),
      ],
    },
    ideal_match: {
      score: 74,
      confidence: 0.74,
      rationale:
        "Researcher-founder with an open-source runtime matches the profile; hardware dependence trims the fit.",
      evidence: [ev("Profile match: education 90, domain-fit 0.78, stars p88.", AX_ZEFIX, "registry")],
    },
  },
});

const TS_REPO = "https://github.com/tactisense/skinprint";
const TS_PAPER = "https://arxiv.org/abs/2601.08832";
const TS_ZEFIX = "https://www.zefix.admin.ch/api/v1/company/uid/CHE-198.407.552";
const TS_PRESS = "https://alpentech-briefing.ch/2026/05/tactisense-printable-skins";
const TS_OPENALEX = "https://api.openalex.org/works/W4408233190";

const tactisense = buildVenture({
  venture_id: TACTISENSE_ID,
  name: "TactiSense",
  one_liner: "Printable tactile skins that give robot arms a sense of touch",
  status: "scored",
  quality_tier: "scored",
  market_tags: ["robotics", "sensors"],
  final_score: 72.8,
  confidence: 0.71,
  funding_signal: "none_found",
  scored_at: "2026-07-14T09:10:00+00:00",
  categories: {
    individual_experience: {
      score: 78,
      confidence: 0.75,
      rationale:
        "Nair holds a PhD on printed capacitive arrays with six first-author papers; Wyss built the lab's fabrication line and owns the printing process.",
      evidence: [
        ev("Six first-author papers on printed tactile sensing.", TS_OPENALEX, "openalex"),
        ev("Wyss maintains the fabrication tooling in skinprint.", TS_REPO, "github"),
      ],
    },
    schools: {
      score: 92,
      confidence: 0.85,
      rationale:
        "Both founders from the same co-supervised ETH Zurich lab — max school tier across members.",
      evidence: [ev("ETH Zurich affiliation for Nair and Wyss.", TS_OPENALEX, "openalex")],
    },
    network_ties: {
      score: 55,
      confidence: 0.6,
      rationale:
        "Coauthor graph reaches sensor-industry researchers but no funded-founder path within two hops.",
      evidence: [ev("No funded founders within 2 hops of the coauthor graph.", TS_OPENALEX, "openalex")],
    },
    prior_collaboration: {
      score: 85,
      confidence: 0.85,
      rationale:
        "Nair and Wyss share four papers and a fabrication repository across three years in the same co-supervised ETH lab.",
      evidence: [
        ev("Four shared papers, 2023–2026.", TS_OPENALEX, "openalex"),
        ev("Shared commits on skinprint since 2023.", TS_REPO, "github"),
      ],
    },
    problem_realness: {
      score: 72,
      confidence: 0.7,
      rationale:
        "Integrators report force-blind grippers damage goods and cap picking speed; damage-rate SLAs are appearing in 3PL contracts.",
      evidence: [ev("Integrators quantify damage rates on force-blind picking.", TS_PRESS, "press")],
    },
    product_defensibility: {
      score: 76,
      confidence: 0.7,
      rationale:
        "Papers cover device physics while printing process windows and the calibration dataset stay proprietary — a process moat that compounds per retrofit.",
      evidence: [
        ev("Process parameters withheld from publication.", TS_PAPER, "arxiv"),
        ev("Per-gripper calibration models in skinprint.", TS_REPO, "github"),
      ],
    },
    market: {
      score: 64,
      confidence: 0.65,
      rationale:
        "End-effector sensing is a niche but grows with e-commerce picking; the retrofit angle reaches the installed base OEM sensing cannot.",
      evidence: [ev("Retrofit segment sizing, May 2026 industry note.", TS_PRESS, "press")],
    },
    traction: {
      score: 50,
      confidence: 0.6,
      rationale:
        "Lab pilots with two European gripper makers; 340 stars on tooling — no revenue signal yet.",
      evidence: [
        ev("Two gripper-maker lab pilots, no commercial terms disclosed.", TS_PRESS, "press"),
        ev("340 stars on skinprint.", TS_REPO, "github"),
      ],
    },
    ideal_match: {
      score: 70,
      confidence: 0.71,
      rationale:
        "Hardware-adjacent researcher founders with verified collaboration fit the thesis well; sector fit is adjacent rather than core.",
      evidence: [ev("Profile match: education 92, domain-fit 0.66.", TS_ZEFIX, "registry")],
    },
  },
});

const FS_REPO = "https://github.com/fastsim-labs/fastsim";
const FS_PAPER = "https://arxiv.org/abs/2603.02417";
const FS_FORUM = "https://news.ycombinator.com/item?id=44098213";

const fastsim = buildVenture({
  venture_id: FASTSIM_ID,
  name: "FastSim Labs",
  one_liner: "Differentiable physics simulation for robot training",
  status: "scored",
  quality_tier: "scored",
  market_tags: ["ai", "simulation"],
  final_score: 70.1,
  confidence: 0.66,
  funding_signal: "none_found",
  scored_at: "2026-07-13T16:20:00+00:00",
  categories: {
    individual_experience: {
      score: 76,
      confidence: 0.7,
      rationale:
        "Berger maintains fastsim, a 4,100-star differentiable physics engine, with 610 commits in 12 months; earlier simulation work is self-reported only.",
      evidence: [ev("610 commits in 12 months on a 4,100-star repo.", FS_REPO, "github")],
    },
    schools: {
      score: null,
      confidence: 0,
      rationale:
        "No degree or institutional affiliation on public record for the sole known member — category excluded and its weight redistributed.",
      evidence: [],
    },
    network_ties: {
      score: 45,
      confidence: 0.55,
      rationale:
        "GitHub collaboration graph touches robotics-learning maintainers; no funded founders within two hops.",
      evidence: [ev("Contributor graph reaches major sim-to-real maintainers.", FS_REPO, "github")],
    },
    prior_collaboration: {
      score: null,
      confidence: 0,
      rationale:
        "Single known member — the prior-collaboration signal is undefined; weight redistributed.",
      evidence: [],
    },
    problem_realness: {
      score: 82,
      confidence: 0.75,
      rationale:
        "The sim-to-real gap is the most-cited bottleneck for robot learning; practitioners report weeks of engineering per new environment.",
      evidence: [ev("Practitioner thread: weeks per environment for contact-rich tasks.", FS_FORUM, "web")],
    },
    product_defensibility: {
      score: 74,
      confidence: 0.65,
      rationale:
        "Gradient-through-contact solver outperforms open baselines in the published benchmark; core solver open, differentiation kernels closed.",
      evidence: [
        ev("Benchmark: 3–8x faster convergence vs open baselines.", FS_PAPER, "arxiv"),
        ev("Closed differentiation kernels noted in the license file.", FS_REPO, "github"),
      ],
    },
    market: {
      score: 70,
      confidence: 0.65,
      rationale: "Robot-training simulation spend grows with fleet learning programs at OEMs and labs.",
      evidence: [ev("Simulation cited as the scaling path for fleet learning.", FS_PAPER, "arxiv")],
    },
    traction: {
      score: 58,
      confidence: 0.6,
      rationale: "4,100 stars with three corporate forks actively syncing; no revenue signal.",
      evidence: [ev("4,100 stars; 3 active corporate forks.", FS_REPO, "github")],
    },
    ideal_match: {
      score: 62,
      confidence: 0.66,
      rationale:
        "Strong open-source signal matches the profile, but the missing education record and solo team weaken the fit.",
      evidence: [ev("Profile match: stars p91, education unknown.", FS_REPO, "github")],
    },
  },
});

const WL_REPO = "https://github.com/wayline-robotics/fleetweave";
const WL_ZEFIX = "https://www.zefix.admin.ch/api/v1/company/uid/CHE-231.559.104";
const WL_PRESS = "https://www.logistikheute-online.de/2026/06/wayline-amr-orchestrierung";
const WL_OPENALEX = "https://api.openalex.org/works/W4407551208";

const wayline = buildVenture({
  venture_id: WAYLINE_ID,
  name: "Wayline Robotics",
  one_liner: "Vendor-neutral orchestration for mixed AMR fleets",
  status: "scored",
  quality_tier: "scored",
  market_tags: ["robotics", "logistics"],
  final_score: 68.6,
  confidence: 0.68,
  funding_signal: "none_found",
  scored_at: "2026-07-13T11:05:00+00:00",
  categories: {
    individual_experience: {
      score: 74,
      confidence: 0.7,
      rationale:
        "Steiner led intralogistics automation projects for eight years at Bern UAS; Kaya published on multi-agent coordination at TU Munich.",
      evidence: [
        ev("Steiner: applied intralogistics project record, 2018–2026.", WL_OPENALEX, "openalex"),
        ev("Kaya: multi-agent coordination publications.", WL_OPENALEX, "openalex"),
      ],
    },
    schools: {
      score: 75,
      confidence: 0.7,
      rationale: "Bern UAS and TU Munich on record — strong applied programs, below the top research tier.",
      evidence: [ev("Affiliations: Bern UAS (Steiner), TU Munich (Kaya).", WL_OPENALEX, "openalex")],
    },
    network_ties: {
      score: 58,
      confidence: 0.6,
      rationale: "Industry-project network across DACH integrators; no funded-founder path found.",
      evidence: [ev("Project partners include three DACH integrators.", WL_PRESS, "press")],
    },
    prior_collaboration: {
      score: 65,
      confidence: 0.7,
      rationale:
        "Steiner and Kaya co-ran a 14-month applied research project on mixed-fleet coordination before founding.",
      evidence: [ev("Joint project report on mixed-fleet coordination, 2025.", WL_OPENALEX, "openalex")],
    },
    problem_realness: {
      score: 76,
      confidence: 0.7,
      rationale:
        "Warehouses running AMRs from multiple vendors report deadlocks and idle zones; vendor lock-in complaints are documented and recurring.",
      evidence: [ev("Mixed-fleet deadlock complaints across three case studies.", WL_PRESS, "press")],
    },
    product_defensibility: {
      score: 62,
      confidence: 0.6,
      rationale:
        "Integration breadth (11 AMR vendors) is a real switching-cost moat, but the orchestration core has limited protectable IP.",
      evidence: [ev("11 vendor adapters listed in fleetweave.", WL_REPO, "github")],
    },
    market: {
      score: 72,
      confidence: 0.7,
      rationale: "AMR fleet growth outpaces single-vendor deployments; orchestration is the natural control point.",
      evidence: [ev("Mixed fleets projected majority of new AMR sites by 2028.", WL_PRESS, "press")],
    },
    traction: {
      score: 61,
      confidence: 0.65,
      rationale: "Two integrator pilots live per the June press note; open-core repo at 720 stars.",
      evidence: [
        ev("Two integrator pilots announced.", WL_PRESS, "press"),
        ev("720 stars on fleetweave.", WL_REPO, "github"),
      ],
    },
    ideal_match: {
      score: 66,
      confidence: 0.68,
      rationale: "Applied-research founders in the core sector; less research pedigree than the ideal profile prefers.",
      evidence: [ev("Profile match: domain-fit 0.81, education 75.", WL_ZEFIX, "registry")],
    },
  },
});

const CB_REPO = "https://github.com/ceresbot/rowvision";
const CB_ZEFIX = "https://www.zefix.admin.ch/api/v1/company/uid/CHE-207.114.886";
const CB_AMTSBLATT = "https://www.amtsblattportal.ch/#!/search/publications/detail/HR02-1204558711";
const CB_PRESS = "https://agrarzukunft.ch/2026/05/ceresbot-feldversuche";
const CB_OPENALEX = "https://api.openalex.org/works/W4406802441";

const ceresbot = buildVenture({
  venture_id: CERESBOT_ID,
  name: "Ceresbot",
  one_liner: "Vision-guided mechanical weeding robots for row crops",
  status: "scored",
  quality_tier: "scored",
  market_tags: ["robotics", "agtech"],
  final_score: 67.0,
  confidence: 0.63,
  funding_signal: "suspected",
  scored_at: "2026-07-12T14:40:00+00:00",
  categories: {
    individual_experience: {
      score: 70,
      confidence: 0.65,
      rationale:
        "Moretti finished an ETH agri-robotics PhD with field-trial publications; Dubois brings EPFL plant-detection vision work.",
      evidence: [
        ev("Moretti: field-robotics PhD record at ETH.", CB_OPENALEX, "openalex"),
        ev("Dubois: crop-vision publications at EPFL.", CB_OPENALEX, "openalex"),
      ],
    },
    schools: {
      score: 86,
      confidence: 0.8,
      rationale: "ETH Zurich and EPFL across the two known members.",
      evidence: [ev("Affiliations: ETH (Moretti), EPFL (Dubois).", CB_OPENALEX, "openalex")],
    },
    network_ties: {
      score: 50,
      confidence: 0.55,
      rationale: "Agri-research network is deep but disjoint from the funded-founder graph.",
      evidence: [ev("No funded founders within 2 hops of the coauthor graph.", CB_OPENALEX, "openalex")],
    },
    prior_collaboration: {
      score: 70,
      confidence: 0.7,
      rationale: "Two seasons of shared field trials and a joint dataset paper before incorporation.",
      evidence: [
        ev("Joint field-trial dataset paper, 2025.", CB_OPENALEX, "openalex"),
        ev("Shared commits on rowvision across two seasons.", CB_REPO, "github"),
      ],
    },
    problem_realness: {
      score: 78,
      confidence: 0.7,
      rationale:
        "EU herbicide restrictions plus seasonal labor shortage make mechanical weeding a forced adoption story in row crops.",
      evidence: [ev("Herbicide-reduction targets driving mechanical alternatives.", CB_PRESS, "press")],
    },
    product_defensibility: {
      score: 58,
      confidence: 0.55,
      rationale:
        "The mechanical approach is replicable; the two-season labeled crop dataset is the main defensible asset.",
      evidence: [ev("Two seasons of labeled row-crop imagery referenced.", CB_REPO, "github")],
    },
    market: {
      score: 66,
      confidence: 0.6,
      rationale:
        "European row-crop weeding is a large seasonal spend, though sales cycles follow harvest calendars.",
      evidence: [ev("Weeding cost per hectare across EU row crops.", CB_PRESS, "press")],
    },
    traction: {
      score: 54,
      confidence: 0.55,
      rationale:
        "Paid trials on three farms this season. An Amtsblatt capital-increase publication suggests possible prior funding — flagged, not confirmed.",
      evidence: [
        ev("Three farm trials in the 2026 season.", CB_PRESS, "press"),
        ev("Capital increase published for Ceresbot AG.", CB_AMTSBLATT, "registry"),
      ],
    },
    ideal_match: {
      score: 60,
      confidence: 0.63,
      rationale: "Researcher founders in hardware-adjacent AI; agtech sits at the edge of the thesis sectors.",
      evidence: [ev("Profile match: education 86, sector adjacency 0.55.", CB_ZEFIX, "registry")],
    },
  },
});

const PS_PAPER = "https://arxiv.org/abs/2512.09904";
const PS_ZEFIX = "https://www.zefix.admin.ch/api/v1/company/uid/CHE-189.320.457";
const PS_PRESS = "https://medtech-observer.eu/2026/04/perisurg-steerable-instruments";
const PS_OPENALEX = "https://api.openalex.org/works/W4405118763";

const perisurg = buildVenture({
  venture_id: PERISURG_ID,
  name: "Périsurg",
  one_liner: "Millimetre-scale steerable instruments for endovascular surgery",
  status: "scored",
  quality_tier: "scored",
  market_tags: ["robotics", "medtech"],
  final_score: 63.2,
  confidence: 0.61,
  funding_signal: "none_found",
  scored_at: "2026-07-12T10:15:00+00:00",
  categories: {
    individual_experience: {
      score: 72,
      confidence: 0.65,
      rationale:
        "Marchand leads a UNIGE medical-robotics group with in-vivo publications; Gruber contributes ETH microfabrication experience.",
      evidence: [
        ev("Marchand: in-vivo steerable-instrument studies.", PS_OPENALEX, "openalex"),
        ev("Gruber: microfabrication methods papers at ETH.", PS_OPENALEX, "openalex"),
      ],
    },
    schools: {
      score: 80,
      confidence: 0.75,
      rationale: "UNIGE faculty plus ETH Zurich — strong academic pedigree across both members.",
      evidence: [ev("Affiliations: UNIGE (Marchand), ETH (Gruber).", PS_OPENALEX, "openalex")],
    },
    network_ties: {
      score: 46,
      confidence: 0.55,
      rationale: "Clinical-research network is strong; ties into the venture ecosystem are thin.",
      evidence: [ev("Coauthor graph is clinical, no funded-founder path.", PS_OPENALEX, "openalex")],
    },
    prior_collaboration: {
      score: 75,
      confidence: 0.75,
      rationale: "Five co-authored papers across four years between the founders' groups.",
      evidence: [ev("Five Marchand–Gruber co-authored papers, 2022–2026.", PS_OPENALEX, "openalex")],
    },
    problem_realness: {
      score: 70,
      confidence: 0.65,
      rationale:
        "Catheter navigation limits which vessels are treatable; interventionists document unmet reach in neurovascular cases.",
      evidence: [ev("Interventionists on untreatable distal vasculature.", PS_PRESS, "press")],
    },
    product_defensibility: {
      score: 72,
      confidence: 0.65,
      rationale:
        "Magnetic steering approach with filed IP and in-vivo data — hard to replicate without the fabrication line.",
      evidence: [
        ev("Priority patent filing referenced in the April press note.", PS_PRESS, "press"),
        ev("In-vivo steering results published.", PS_PAPER, "arxiv"),
      ],
    },
    market: {
      score: 48,
      confidence: 0.55,
      rationale:
        "Endovascular instruments are a large market, but the regulatory path pushes revenue years out — the near-term serviceable market is narrow.",
      evidence: [ev("CE-marking path estimated at 3+ years.", PS_PRESS, "press")],
    },
    traction: {
      score: 30,
      confidence: 0.5,
      rationale: "Preclinical only: benchtop and animal studies, no commercial agreements.",
      evidence: [ev("Preclinical status as of April 2026.", PS_PRESS, "press")],
    },
    ideal_match: {
      score: 55,
      confidence: 0.61,
      rationale: "Deep-tech researcher founders fit; medtech timelines sit outside the pre-seed sweet spot.",
      evidence: [ev("Profile match: education 80, stage-fit 0.4.", PS_ZEFIX, "registry")],
    },
  },
});

const CS_REPO = "https://github.com/cairnsight/ridgeline";
const CS_ZEFIX = "https://www.zefix.admin.ch/api/v1/company/uid/CHE-225.671.930";
const CS_PRESS = "https://alpentech-briefing.ch/2026/06/cairnsight-alpine-inspektion";
const CS_OPENALEX = "https://api.openalex.org/works/W4404290187";

const cairnsight = buildVenture({
  venture_id: CAIRNSIGHT_ID,
  name: "CairnSight",
  one_liner: "Autonomous drone inspection of alpine energy infrastructure",
  status: "scored",
  quality_tier: "scored",
  market_tags: ["ai", "robotics", "energy"],
  final_score: 60.7,
  confidence: 0.58,
  funding_signal: "none_found",
  scored_at: "2026-07-11T15:50:00+00:00",
  categories: {
    individual_experience: {
      score: 64,
      confidence: 0.6,
      rationale:
        "Zimmermann ran drone-survey projects at Bern UAS for five years; Halvorsen contributes DTU wind-turbine inspection research.",
      evidence: [
        ev("Zimmermann: applied drone-survey project record.", CS_OPENALEX, "openalex"),
        ev("Halvorsen: turbine-inspection papers at DTU.", CS_OPENALEX, "openalex"),
      ],
    },
    schools: {
      score: 70,
      confidence: 0.65,
      rationale: "Bern UAS and DTU on record — solid applied engineering programs.",
      evidence: [ev("Affiliations: Bern UAS, DTU.", CS_OPENALEX, "openalex")],
    },
    network_ties: {
      score: 40,
      confidence: 0.5,
      rationale: "Utility-sector contacts from survey work; no venture-network signal.",
      evidence: [ev("Project history with two Swiss utilities.", CS_PRESS, "press")],
    },
    prior_collaboration: {
      score: 60,
      confidence: 0.6,
      rationale: "One joint inspection-methods paper and a season of shared fieldwork.",
      evidence: [ev("Joint inspection-methods paper, 2025.", CS_OPENALEX, "openalex")],
    },
    problem_realness: {
      score: 68,
      confidence: 0.65,
      rationale:
        "Avalanche-prone pylons and high dams are costly and dangerous to inspect by helicopter and rope crew; utilities document the spend.",
      evidence: [ev("Helicopter-inspection costs per alpine line-km.", CS_PRESS, "press")],
    },
    product_defensibility: {
      score: 58,
      confidence: 0.55,
      rationale:
        "Alpine-specific route planning and defect models add value, but the airframes and base autonomy are off-the-shelf.",
      evidence: [ev("Route-planning models in ridgeline; COTS airframes.", CS_REPO, "github")],
    },
    market: {
      score: 62,
      confidence: 0.6,
      rationale: "Energy-infrastructure inspection is a steady spend; the alpine niche is defensible but bounded.",
      evidence: [ev("Swiss grid inspection budget figures.", CS_PRESS, "press")],
    },
    traction: {
      score: 58,
      confidence: 0.6,
      rationale: "One paid survey completed for a grid operator; a second utility trial scheduled for autumn.",
      evidence: [ev("Paid pylon survey for a grid operator, June 2026.", CS_PRESS, "press")],
    },
    ideal_match: {
      score: 52,
      confidence: 0.58,
      rationale:
        "Applied founders in an adjacent sector; weaker research and open-source signal than the profile targets.",
      evidence: [ev("Profile match: domain-fit 0.58, education 70.", CS_ZEFIX, "registry")],
    },
  },
});

const LW_PAPER = "https://arxiv.org/abs/2604.01286";
const LW_CLUSTER = "https://api.openalex.org/works/W4409556021";
const LW_CVR = "https://datacvr.virk.dk/enhed/virksomhed/45219903";

const loopwise = buildVenture({
  venture_id: LOOPWISE_ID,
  name: "Loopwise",
  one_liner: "SLAM foundation models from a KTH–DTU paper cluster",
  status: "scored",
  quality_tier: "scored",
  market_tags: ["ai", "robotics"],
  final_score: 57.2,
  confidence: 0.41,
  funding_signal: "suspected",
  scored_at: "2026-07-11T09:25:00+00:00",
  categories: {
    individual_experience: {
      score: 66,
      confidence: 0.5,
      rationale:
        "Patel and Sørensen anchor a well-cited SLAM publication cluster; no shipped systems or maintained repositories on record.",
      evidence: [ev("Citation-weighted SLAM cluster, 2023–2026.", LW_CLUSTER, "openalex")],
    },
    schools: {
      score: 82,
      confidence: 0.6,
      rationale: "KTH and DTU across the two known members.",
      evidence: [ev("Affiliations: KTH (Patel), DTU (Sørensen).", LW_CLUSTER, "openalex")],
    },
    network_ties: {
      score: 36,
      confidence: 0.4,
      rationale: "Academic network only; no path to funded founders found.",
      evidence: [ev("Coauthor graph confined to academic SLAM groups.", LW_CLUSTER, "openalex")],
    },
    prior_collaboration: {
      score: 80,
      confidence: 0.6,
      rationale:
        "Six shared papers across three years in the KTH–DTU cluster — deep, verified research collaboration.",
      evidence: [ev("Six Patel–Sørensen co-authored papers, 2023–2026.", LW_CLUSTER, "openalex")],
    },
    problem_realness: {
      score: 62,
      confidence: 0.5,
      rationale:
        "Per-deployment SLAM tuning is a documented integrator cost; a foundation-model approach is plausible but unproven.",
      evidence: [ev("SLAM tuning effort cited in the position paper.", LW_PAPER, "arxiv")],
    },
    product_defensibility: {
      score: 48,
      confidence: 0.4,
      rationale:
        "Models are unreleased; differentiation against strong open baselines is asserted in preprints, not demonstrated.",
      evidence: [ev("Benchmark claims in preprint, no released weights.", LW_PAPER, "arxiv")],
    },
    market: {
      score: 50,
      confidence: 0.45,
      rationale: "Localization software is mostly bundled today; a standalone market is emerging but unproven.",
      evidence: [ev("SLAM licensing mostly bundled with platforms.", LW_PAPER, "arxiv")],
    },
    traction: {
      score: 30,
      confidence: 0.35,
      rationale:
        "Preprints only — no public repository or users. A Danish CVR entry for a Loopwise ApS with paid-in capital above the minimum suggests possible prior funding.",
      evidence: [
        ev("No public code artifacts found.", LW_PAPER, "arxiv"),
        ev("Loopwise ApS registered with DKK 400k paid-in capital.", LW_CVR, "registry"),
      ],
    },
    ideal_match: {
      score: 48,
      confidence: 0.41,
      rationale: "Research pedigree fits; missing open-source signal and unclear commitment lower the match.",
      evidence: [ev("Profile match: education 82, stars n/a.", LW_CLUSTER, "openalex")],
    },
  },
});

const OX_ZEFIX = "https://www.zefix.admin.ch/api/v1/company/uid/CHE-243.998.017";
const OX_AMTSBLATT = "https://www.amtsblattportal.ch/#!/search/publications/detail/HR02-1204990233";

const otterix = buildVenture({
  venture_id: OTTERIX_ID,
  name: "Otterix Automation",
  one_liner: "Stealth industrial automation venture (registry signal only)",
  status: "sourced",
  quality_tier: "needs_more_data",
  market_tags: ["robotics"],
  final_score: 43.7,
  confidence: 0.28,
  funding_signal: "none_found",
  scored_at: "2026-07-16T07:45:00+00:00",
  categories: {
    individual_experience: {
      score: 40,
      confidence: 0.3,
      rationale:
        'Sole registry officer "R. Vogel" could not be resolved against GitHub, ORCID, or publication records — no verifiable track record.',
      evidence: [ev("Officer R. Vogel listed on incorporation.", OX_ZEFIX, "registry")],
    },
    schools: {
      score: null,
      confidence: 0,
      rationale: "No affiliations resolvable from a registry-only signal; weight redistributed.",
      evidence: [],
    },
    network_ties: {
      score: 25,
      confidence: 0.25,
      rationale: "No coauthor or code graph exists for the sole named officer.",
      evidence: [ev("No graph matches for R. Vogel.", OX_ZEFIX, "registry")],
    },
    prior_collaboration: {
      score: null,
      confidence: 0,
      rationale: "Single unresolved officer — collaboration signal undefined; weight redistributed.",
      evidence: [],
    },
    problem_realness: {
      score: 50,
      confidence: 0.35,
      rationale:
        "The commercial-register purpose names industrial automation retrofits — a real problem space, but nothing verifiable beyond the filing.",
      evidence: [ev("Purpose: development of industrial automation systems.", OX_AMTSBLATT, "registry")],
    },
    product_defensibility: {
      score: null,
      confidence: 0,
      rationale: "No product, code, or filings observable; category excluded and weight redistributed.",
      evidence: [],
    },
    market: {
      score: 55,
      confidence: 0.4,
      rationale: "Industrial automation retrofit demand is well documented across DACH SMEs.",
      evidence: [ev("Retrofit demand across DACH manufacturing SMEs.", OX_AMTSBLATT, "registry")],
    },
    traction: {
      score: null,
      confidence: 0,
      rationale: "No observable traction signal of any kind; category excluded.",
      evidence: [],
    },
    ideal_match: {
      score: 38,
      confidence: 0.28,
      rationale: "Sector matches the thesis; every people-level feature of the ideal profile is unknown.",
      evidence: [ev("Registry-only signal; profile features unresolved.", OX_ZEFIX, "registry")],
    },
  },
});

export const EXTRA_VENTURES: RankedVenture[] = [
  axonode,
  tactisense,
  fastsim,
  wayline,
  ceresbot,
  perisurg,
  cairnsight,
  loopwise,
  otterix,
];

// ---------------------------------------------------------------------------
// Teams
// ---------------------------------------------------------------------------

interface MemberInput {
  venture_id: string;
  person_id: string;
  full_name: string;
  headline?: string | null;
  github_login?: string | null;
  orcid?: string | null;
  linkedin_url?: string | null;
  affiliation?: string | null;
  avatar_url?: string | null;
  role_hint?: string | null;
  is_founder_guess: boolean;
  weight: number;
  evidence?: Record<string, unknown> | null;
}

function member(m: MemberInput): VentureTeamMember {
  return {
    venture_id: m.venture_id,
    person_id: m.person_id,
    full_name: m.full_name,
    headline: m.headline ?? null,
    github_login: m.github_login ?? null,
    orcid: m.orcid ?? null,
    linkedin_url: m.linkedin_url ?? null,
    affiliation: m.affiliation ?? null,
    avatar_url: m.avatar_url ?? null,
    role_hint: m.role_hint ?? null,
    is_founder_guess: m.is_founder_guess,
    weight: m.weight,
    evidence: m.evidence ?? null,
  };
}

export const EXTRA_TEAM: Record<string, VentureTeamMember[]> = {
  [AXONODE_ID]: [
    member({
      venture_id: AXONODE_ID,
      person_id: "dddd0001-0000-4000-8000-000000000001",
      full_name: "Dr. Matteo Ricci",
      headline: "Neuromorphic-inference postdoc building spikeflow.",
      github_login: "matteoricci-neuro",
      orcid: "0000-0003-2914-6608",
      affiliation: "EPFL",
      avatar_url: "https://avatars.example.com/u/502001",
      role_hint: "founder",
      is_founder_guess: true,
      weight: 0.6,
      evidence: { contribution_share: 0.6 },
    }),
    member({
      venture_id: AXONODE_ID,
      person_id: "dddd0002-0000-4000-8000-000000000002",
      full_name: "Sofia Lindqvist",
      headline: "Embedded flight-systems engineer, ex two drone programs.",
      github_login: "slindqvist",
      affiliation: "KTH Royal Institute of Technology",
      avatar_url: "https://avatars.example.com/u/502002",
      role_hint: "co-founder",
      is_founder_guess: true,
      weight: 0.4,
      evidence: { contribution_share: 0.4 },
    }),
  ],
  [TACTISENSE_ID]: [
    member({
      venture_id: TACTISENSE_ID,
      person_id: "dddd0003-0000-4000-8000-000000000003",
      full_name: "Dr. Priya Nair",
      headline: "Printed tactile sensing researcher; leads TactiSense.",
      github_login: "priyanair-haptics",
      orcid: "0000-0002-7130-4415",
      affiliation: "ETH Zürich",
      avatar_url: "https://avatars.example.com/u/502003",
      role_hint: "founder",
      is_founder_guess: true,
      weight: 0.55,
      evidence: { contribution_share: 0.55 },
    }),
    member({
      venture_id: TACTISENSE_ID,
      person_id: "dddd0004-0000-4000-8000-000000000004",
      full_name: "Jonas Wyss",
      headline: "Fabrication engineer; owns the sensor printing line.",
      github_login: "jwyss-fab",
      affiliation: "ETH Zürich",
      avatar_url: "https://avatars.example.com/u/502004",
      role_hint: "co-founder",
      is_founder_guess: true,
      weight: 0.45,
      evidence: { contribution_share: 0.45 },
    }),
  ],
  [FASTSIM_ID]: [
    member({
      venture_id: FASTSIM_ID,
      // Reuses the fixture person — Nils Berger exists in generated.ts.
      person_id: NILS_BERGER_PERSON_ID,
      full_name: "Nils Berger",
      headline: "Simulation engineer behind FastSim.",
      github_login: "nilsberger",
      affiliation: null, // no affiliation on record — schools/collab honestly N/A
      role_hint: "founder",
      is_founder_guess: true,
      weight: 1,
      evidence: { contribution_share: 1 },
    }),
  ],
  [WAYLINE_ID]: [
    member({
      venture_id: WAYLINE_ID,
      person_id: "dddd0005-0000-4000-8000-000000000005",
      full_name: "Fabian Steiner",
      headline: "Intralogistics automation lead turned founder.",
      github_login: "fsteiner-amr",
      affiliation: "Bern University of Applied Sciences",
      avatar_url: "https://avatars.example.com/u/502005",
      role_hint: "founder",
      is_founder_guess: true,
      weight: 0.6,
      evidence: { contribution_share: 0.6 },
    }),
    member({
      venture_id: WAYLINE_ID,
      person_id: "dddd0006-0000-4000-8000-000000000006",
      full_name: "Elif Kaya",
      headline: "Multi-agent coordination researcher.",
      github_login: "elifkaya-mas",
      orcid: "0000-0001-8834-2276",
      affiliation: "TU Munich",
      avatar_url: "https://avatars.example.com/u/502006",
      role_hint: "co-founder",
      is_founder_guess: true,
      weight: 0.4,
      evidence: { contribution_share: 0.4 },
    }),
  ],
  [CERESBOT_ID]: [
    member({
      venture_id: CERESBOT_ID,
      person_id: "dddd0007-0000-4000-8000-000000000007",
      full_name: "Luca Moretti",
      headline: "Agri-robotics PhD; two seasons of weeding field trials.",
      github_login: "lmoretti-agri",
      orcid: "0000-0002-5521-9083",
      affiliation: "ETH Zürich",
      avatar_url: "https://avatars.example.com/u/502007",
      role_hint: "founder",
      is_founder_guess: true,
      weight: 0.6,
      evidence: { contribution_share: 0.6 },
    }),
    member({
      venture_id: CERESBOT_ID,
      person_id: "dddd0008-0000-4000-8000-000000000008",
      full_name: "Marie Dubois",
      headline: "Crop-vision researcher.",
      github_login: "mdubois-vision",
      affiliation: "EPFL",
      avatar_url: "https://avatars.example.com/u/502008",
      role_hint: "co-founder",
      is_founder_guess: true,
      weight: 0.4,
      evidence: { contribution_share: 0.4 },
    }),
  ],
  [PERISURG_ID]: [
    member({
      venture_id: PERISURG_ID,
      person_id: "dddd0009-0000-4000-8000-000000000009",
      full_name: "Dr. Élodie Marchand",
      headline: "Medical-robotics group lead working on steerable instruments.",
      orcid: "0000-0003-4471-8850",
      affiliation: "University of Geneva",
      avatar_url: "https://avatars.example.com/u/502009",
      role_hint: "founder",
      is_founder_guess: true,
      weight: 0.65,
      evidence: { contribution_share: 0.65 },
    }),
    member({
      venture_id: PERISURG_ID,
      person_id: "dddd000a-0000-4000-8000-00000000000a",
      full_name: "Stefan Gruber",
      headline: "Microrobotics and microfabrication engineer.",
      github_login: "sgruber-micro",
      affiliation: "ETH Zürich",
      avatar_url: "https://avatars.example.com/u/502010",
      role_hint: "co-founder",
      is_founder_guess: true,
      weight: 0.35,
      evidence: { contribution_share: 0.35 },
    }),
  ],
  [CAIRNSIGHT_ID]: [
    member({
      venture_id: CAIRNSIGHT_ID,
      person_id: "dddd000b-0000-4000-8000-00000000000b",
      full_name: "Reto Zimmermann",
      headline: "Drone-survey engineer for alpine infrastructure.",
      github_login: "rzimmermann-uav",
      affiliation: "Bern University of Applied Sciences",
      avatar_url: "https://avatars.example.com/u/502011",
      role_hint: "founder",
      is_founder_guess: true,
      weight: 0.7,
      evidence: { contribution_share: 0.7 },
    }),
    member({
      venture_id: CAIRNSIGHT_ID,
      person_id: "dddd000c-0000-4000-8000-00000000000c",
      full_name: "Ingrid Halvorsen",
      headline: "Wind-energy inspection researcher.",
      orcid: "0000-0001-9917-5532",
      affiliation: "DTU",
      avatar_url: "https://avatars.example.com/u/502012",
      role_hint: "co-founder",
      is_founder_guess: true,
      weight: 0.3,
      evidence: { contribution_share: 0.3 },
    }),
  ],
  [LOOPWISE_ID]: [
    member({
      venture_id: LOOPWISE_ID,
      // Reuses the fixture person — Aisha Patel exists in generated.ts.
      person_id: AISHA_PATEL_PERSON_ID,
      full_name: "Aisha Patel",
      headline: "SLAM researcher at KTH.",
      orcid: "0000-0001-5109-3700",
      affiliation: "KTH Royal Institute of Technology",
      role_hint: "founder",
      is_founder_guess: true,
      weight: 0.5,
      evidence: { coauthor_cluster: "KTH-DTU SLAM" },
    }),
    member({
      venture_id: LOOPWISE_ID,
      person_id: "dddd000d-0000-4000-8000-00000000000d",
      full_name: "Dr. Henrik Sørensen",
      headline: "SLAM and state-estimation researcher.",
      orcid: "0000-0002-3308-7741",
      affiliation: "DTU",
      avatar_url: "https://avatars.example.com/u/502013",
      role_hint: "co-founder",
      is_founder_guess: true,
      weight: 0.5,
      evidence: { coauthor_cluster: "KTH-DTU SLAM" },
    }),
  ],
  [OTTERIX_ID]: [
    member({
      venture_id: OTTERIX_ID,
      person_id: "dddd000e-0000-4000-8000-00000000000e",
      full_name: "R. Vogel",
      headline: null,
      affiliation: null,
      avatar_url: null, // unresolved officer — no avatar by design
      role_hint: "registered officer",
      is_founder_guess: false,
      weight: 1,
      evidence: { officer_role: "member of the board", resolved: false },
    }),
  ],
};

// ---------------------------------------------------------------------------
// GraspLab gaps — REPLACES the generated fixture gaps in the seed merge.
// ---------------------------------------------------------------------------

const GAPS_CREATED_AT = "2026-07-15T09:00:00+00:00";

export const EXTRA_GAPS: Record<string, VentureGap[]> = {
  [GRASPLAB]: [
    {
      venture_id: GRASPLAB,
      category: "traction",
      field: "traction.revenue",
      importance: 0.9,
      question_text: "Do you have paying pilots or revenue today?",
      created_at: GAPS_CREATED_AT,
    },
    {
      venture_id: GRASPLAB,
      category: "market",
      field: "market.tam",
      importance: 0.7,
      question_text: "Which customer segment do you serve first, and how large is it?",
      created_at: GAPS_CREATED_AT,
    },
    {
      venture_id: GRASPLAB,
      category: "individual_experience",
      field: "team.commitment",
      importance: 0.62,
      question_text: "Are you and Wei both full-time on GraspLab?",
      created_at: GAPS_CREATED_AT,
    },
    {
      venture_id: GRASPLAB,
      category: "product_defensibility",
      field: "tech.ip_licensing",
      importance: 0.55,
      question_text: "How is the ETH research IP licensed to the company?",
      created_at: GAPS_CREATED_AT,
    },
    {
      venture_id: GRASPLAB,
      category: "traction",
      field: "funding.history_verified",
      importance: 0.5,
      question_text: "Our records show no prior venture funding — is that right?",
      created_at: GAPS_CREATED_AT,
    },
  ],
};

// ---------------------------------------------------------------------------
// Memos — Axonode and TactiSense only; other extras intentionally have none
// (the UI shows its branded "no memo yet" state for them).
// ---------------------------------------------------------------------------

export const EXTRA_MEMOS: Record<string, Memo> = {
  [AXONODE_ID]: {
    memo_id: "memo-axonode-1",
    venture_id: AXONODE_ID,
    thesis_id: THESIS_ID,
    sections: AXONODE_MEMO_SECTIONS,
    model_version: "fixture-memo-1",
    status: "draft",
    run_id: null,
    generated_at: "2026-07-14T09:00:00+00:00",
    is_latest: true,
  },
  [TACTISENSE_ID]: {
    memo_id: "memo-tactisense-1",
    venture_id: TACTISENSE_ID,
    thesis_id: THESIS_ID,
    sections: TACTISENSE_MEMO_SECTIONS,
    model_version: "fixture-memo-1",
    status: "draft",
    run_id: null,
    generated_at: "2026-07-14T09:30:00+00:00",
    is_latest: true,
  },
};
