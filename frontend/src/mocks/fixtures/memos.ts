/**
 * Hand-authored memo sections (memo.schema.json, schema_version 1).
 *
 * - GraspLab PRE: the memo as scored from public data only — the five gap
 *   fields appear as `missing: true` bullets and TAM/SAM/SOM stay null.
 * - GraspLab POST: the same memo after the consent-based interview — every
 *   gap is filled by an interview-cited bullet (source_type "interview").
 * - Axonode / TactiSense: full public-data memos for the two runners-up.
 *
 * All companies, people, outlets, and URLs are fictional; URLs are shaped
 * like the real registries/hosts they imitate but resolve to nothing real.
 */
import type { Evidence, MemoBullet, MemoSections } from "@/lib/domain/types";

/** The GraspLab interview record (gold.interview fixture) as a citable source. */
const INTERVIEW_URL = "app://interview/bbbbbbbb-0000-4000-8000-000000000005";

const ev = (claim: string, source_url: string, source_type: string): Evidence => ({
  claim,
  source_url,
  source_type,
});

const cite = (text: string, ...evidence: Evidence[]): MemoBullet => ({ text, evidence });

const gap = (text: string, gap_field: string): MemoBullet => ({
  text,
  missing: true,
  gap_field,
});

const interviewCite = (text: string, claim: string): MemoBullet => ({
  text,
  evidence: [ev(claim, INTERVIEW_URL, "interview")],
});

// --- GraspLab source URLs (shared with the generated fixtures) ---

const GL_REPO = "https://github.com/grasplab/grasp-anything";
const GL_PAPER = "https://arxiv.org/abs/2506.11111";
const GL_ZEFIX = "https://www.zefix.admin.ch/api/v1/company/uid/CHE-123.456.789";
const GL_OPENALEX = "https://api.openalex.org/works/W4400000001";
const GL_FORUM = "https://news.ycombinator.com/item?id=fixture";
const GL_MARKET = "https://example.com/market-report";

// ---------------------------------------------------------------------------
// GraspLab — PRE-interview memo (public data only; five gaps open)
// ---------------------------------------------------------------------------

export const GRASPLAB_MEMO_PRE_SECTIONS: MemoSections = {
  schema_version: 1,
  company_snapshot: {
    bullets: [
      cite(
        "GraspLab AG is an ETH Zurich spin-off incorporated in Zurich in June 2026 (Zefix CHE-123.456.789).",
        ev("GraspLab AG registered 2026-06-20, seat Zurich.", GL_ZEFIX, "registry"),
      ),
      cite(
        "Two team members known from public data: Léna Fischer (founder signal, 62% of commits) and Wei Zhang (maintainer, 38%).",
        ev("Commit shares 0.62 / 0.38 on grasp-anything.", GL_REPO, "github"),
      ),
      cite(
        "Ships GraspFM, an open foundation model for robotic grasping — 8,200-star repository plus a peer-visible paper.",
        ev("grasp-anything: 8,200 stars, 410 forks.", GL_REPO, "github"),
        ev("GraspFM: A Foundation Model for Robotic Grasping (2026).", GL_PAPER, "arxiv"),
      ),
    ],
  },
  investment_hypotheses: {
    bullets: [
      cite(
        "Grasp reliability is the operational bottleneck in warehouse automation — solving it unlocks stalled picking deployments.",
        ev("Recurring practitioner complaints about grasping reliability.", GL_FORUM, "web"),
      ),
      cite(
        "The open foundation model is the wedge: a permissive core drives integrator adoption while commercial weights monetize production use.",
        ev("Permissive core license with commercial weights tier.", GL_REPO, "github"),
      ),
      cite(
        "ETH talent moat: researcher-founders with first-author manipulation work are rare and hard to replicate.",
        ev("First-author GraspFM publication linked to ETH Zurich.", GL_OPENALEX, "openalex"),
      ),
    ],
  },
  swot: {
    bullets: [
      cite(
        "Strength: 8,200-star repository in 4 months plus the GraspFM paper — top-decile open-source and research signal.",
        ev("8,200 stars in 4 months.", GL_REPO, "github"),
        ev("GraspFM paper, June 2026.", GL_PAPER, "arxiv"),
      ),
      gap("Weakness: no verified revenue — paying-pilot status unknown from public data.", "traction.revenue"),
      cite(
        "Opportunity: the DACH 3PL segment retrofits existing warehouses and is underserved by arm-vendor software.",
        ev("DACH 3PLs cited as an underserved retrofit segment.", GL_MARKET, "web"),
      ),
      cite(
        "Threat: large robotics vendors bundle in-house grasping stacks with their hardware.",
        ev("In-house grasping stacks at large robotics vendors.", GL_MARKET, "web"),
      ),
    ],
  },
  team_and_history: {
    bullets: [
      cite(
        "Léna Fischer: 62% of commits on grasp-anything and first author on GraspFM — the technical center of gravity.",
        ev("Contribution share 0.62; first-author on GraspFM.", GL_REPO, "github"),
        ev("GraspFM author list, position 1.", GL_PAPER, "arxiv"),
      ),
      cite(
        "Wei Zhang: 38% of commits with a steady weekly cadence since March 2026.",
        ev("Contribution share 0.38, weekly commit cadence.", GL_REPO, "github"),
      ),
      cite(
        "Fischer and Zhang share a paper and a repository across 4 months — verified prior collaboration, not a hackathon pairing.",
        ev("Shared paper and repo across 4 months.", GL_OPENALEX, "openalex"),
      ),
    ],
  },
  problem_and_product: {
    bullets: [
      cite(
        "Practitioners repeatedly report grasp failures as the reason picking cells run below rated throughput.",
        ev("Recurring complaints about grasping reliability in warehouse automation.", GL_FORUM, "web"),
      ),
      cite(
        "Warehouses pay for manual workarounds today — exception handlers re-picking what grippers drop — which is budget a software fix can capture.",
        ev("Manual exception handling cited as standard practice in picking cells.", GL_MARKET, "web"),
      ),
      cite(
        "GraspFM is their own foundation model with a published training recipe — not a wrapper over someone else's API.",
        ev("Model architecture and training recipe published.", GL_PAPER, "arxiv"),
      ),
    ],
  },
  technology_and_defensibility: {
    bullets: [
      cite(
        "Training recipe is published and reproduced by third parties — credibility, plus a data flywheel from deployments the paper cannot commoditize.",
        ev("Training recipe published with reference implementation.", GL_PAPER, "arxiv"),
      ),
      cite(
        "Licensing splits a permissive core from commercial production weights — adoption and monetization are structurally separated.",
        ev("Permissive core + commercial weights licensing.", GL_REPO, "github"),
      ),
      gap(
        "How the ETH research IP is licensed to the company is unconfirmed — spin-off terms can range from benign to encumbering.",
        "tech.ip_licensing",
      ),
    ],
  },
  market_tam_sam_som: {
    tam: null,
    sam: null,
    som: null,
    assumptions: [
      "Warehouse-automation software spend in Europe keeps double-digit growth through 2030.",
      "Grasping software is priced as a per-site annual subscription.",
    ],
    bullets: [
      cite(
        "Robotic manipulation demand is growing with named competitors investing — the category is real even before bottom-up sizing.",
        ev("Robotic manipulation TAM growing with named competitors.", GL_MARKET, "web"),
      ),
      gap(
        "Bottom-up TAM/SAM/SOM not yet computed — the first customer segment and its size are unconfirmed.",
        "market.tam",
      ),
    ],
  },
  competition: {
    bullets: [
      cite(
        "Competitive density is moderate: grasping intelligence mostly ships as a hardware-vendor feature, not a standalone product.",
        ev("Competes with in-house grasping stacks at large robotics vendors.", GL_MARKET, "web"),
      ),
      cite(
        "GreifTech Systems (Munich) bundles a proprietary grasp planner with its arms — strong in automotive, weak in mixed-SKU 3PL.",
        ev("GreifTech grasp planner ships only with GreifTech arms.", GL_MARKET, "web"),
      ),
      cite(
        "Volkert Automation sells PickSuite through integrator accounts; closed stack, no foundation-model roadmap visible.",
        ev("PickSuite positioned as a closed integrator add-on.", GL_MARKET, "web"),
      ),
    ],
  },
  traction_and_kpis: {
    bullets: [
      cite(
        "8,200 GitHub stars in 4 months (top-decile for robotics OSS) and 410 forks — adoption signal is unusually strong.",
        ev("8,200 stars, 410 forks on grasp-anything.", GL_REPO, "github"),
      ),
      gap("Revenue and paying-pilot status unverified from public data.", "traction.revenue"),
      gap("Founder full-time commitment unconfirmed.", "team.commitment"),
      gap("No prior venture funding found — needs confirmation from the team.", "funding.history_verified"),
    ],
  },
};

// ---------------------------------------------------------------------------
// GraspLab — POST-interview memo (gaps filled with interview-cited bullets)
// ---------------------------------------------------------------------------

export const GRASPLAB_MEMO_POST_SECTIONS: MemoSections = {
  schema_version: 1,
  company_snapshot: GRASPLAB_MEMO_PRE_SECTIONS.company_snapshot,
  investment_hypotheses: GRASPLAB_MEMO_PRE_SECTIONS.investment_hypotheses,
  swot: {
    bullets: [
      cite(
        "Strength: 8,200-star repository in 4 months plus the GraspFM paper — top-decile open-source and research signal.",
        ev("8,200 stars in 4 months.", GL_REPO, "github"),
        ev("GraspFM paper, June 2026.", GL_PAPER, "arxiv"),
      ),
      interviewCite(
        "Weakness: revenue is real but early and concentrated — three paid pilots, all warehouse logistics, ~CHF 12k MRR.",
        "Three paid pilots at CHF 4,000/month each (~CHF 12k MRR), all in warehouse logistics.",
      ),
      cite(
        "Opportunity: the DACH 3PL segment retrofits existing warehouses and is underserved by arm-vendor software.",
        ev("DACH 3PLs cited as an underserved retrofit segment.", GL_MARKET, "web"),
      ),
      cite(
        "Threat: large robotics vendors bundle in-house grasping stacks with their hardware.",
        ev("In-house grasping stacks at large robotics vendors.", GL_MARKET, "web"),
      ),
    ],
  },
  team_and_history: {
    bullets: [
      ...GRASPLAB_MEMO_PRE_SECTIONS.team_and_history.bullets,
      interviewCite(
        "Commitment confirmed in interview: Fischer full-time since June; Zhang defends his PhD in August and is signed to join full-time September 1, already holding founder equity.",
        "Fischer full-time since June 2026; Zhang signed to join full-time on 2026-09-01 with founder equity.",
      ),
    ],
  },
  problem_and_product: GRASPLAB_MEMO_PRE_SECTIONS.problem_and_product,
  technology_and_defensibility: {
    bullets: [
      cite(
        "Training recipe is published and reproduced by third parties — credibility, plus a data flywheel from deployments the paper cannot commoditize.",
        ev("Training recipe published with reference implementation.", GL_PAPER, "arxiv"),
      ),
      cite(
        "Licensing splits a permissive core from commercial production weights — adoption and monetization are structurally separated.",
        ev("Permissive core + commercial weights licensing.", GL_REPO, "github"),
      ),
      interviewCite(
        "IP confirmed in interview: exclusive licence from ETH transfer signed 2026-06-28 on standard spin-off terms; model weights and training pipeline owned outright.",
        "Exclusive ETH licence signed 2026-06-28; weights and pipeline owned by GraspLab AG.",
      ),
    ],
  },
  market_tam_sam_som: {
    tam: "CHF 2.1B — global software for robotic picking and grasping (2030 projection)",
    sam: "CHF 480M — European mid-size warehouse-automation retrofits",
    som: "CHF 115M — 1,900 DACH mid-size 3PL sites × CHF 60k/yr",
    assumptions: [
      "1,900 mid-size 3PL sites in DACH (founder estimate, interview 2026-07-16).",
      "CHF 60k average contract value per site per year at current pilot pricing.",
      "Warehouse-automation software spend in Europe keeps double-digit growth through 2030.",
    ],
    bullets: [
      cite(
        "Robotic manipulation demand is growing with named competitors investing — the category is real even before bottom-up sizing.",
        ev("Robotic manipulation TAM growing with named competitors.", GL_MARKET, "web"),
      ),
      interviewCite(
        "First segment confirmed in interview: mid-size 3PL warehouses in DACH — roughly 1,900 sites, ≈ CHF 115M serviceable before the rest of Europe.",
        "First segment: mid-size DACH 3PL warehouses; ~1,900 sites × CHF 60k/yr ≈ CHF 115M SOM.",
      ),
    ],
  },
  competition: GRASPLAB_MEMO_PRE_SECTIONS.competition,
  traction_and_kpis: {
    bullets: [
      cite(
        "8,200 GitHub stars in 4 months (top-decile for robotics OSS) and 410 forks — adoption signal is unusually strong.",
        ev("8,200 stars, 410 forks on grasp-anything.", GL_REPO, "github"),
      ),
      interviewCite(
        "Revenue confirmed in interview: three paid pilots at CHF 4k/month (~CHF 12k MRR); lead pilot at 96.3% pick success on a 500-SKU set, two conversion decisions scheduled for December.",
        "3 paid pilots, CHF 4,000/month each; lead pilot 96.3% pick success; conversions scheduled for December.",
      ),
      interviewCite(
        "Funding history confirmed: no prior equity of any kind — a CHF 150k non-dilutive grant plus pilot fees; runway ≈ 11 months at CHF 14k/month burn.",
        "No prior equity funding; CHF 150k non-dilutive grant; ~11 months runway at CHF 14k/month burn.",
      ),
      interviewCite(
        "Unannounced demand signal: a 41-company design-partner waitlist the founder weighs above the star count.",
        "41-company design-partner waitlist, never announced publicly.",
      ),
    ],
  },
};

// ---------------------------------------------------------------------------
// Axonode — public-data memo
// ---------------------------------------------------------------------------

const AX_REPO = "https://github.com/axonode-ai/spikeflow";
const AX_PAPER = "https://arxiv.org/abs/2602.10771";
const AX_ZEFIX = "https://www.zefix.admin.ch/api/v1/company/uid/CHE-214.882.331";
const AX_PRESS = "https://www.roboticsweekly.eu/2026/06/axonode-neuromorphic-drones";
const AX_OPENALEX = "https://api.openalex.org/works/W4409120344";

export const AXONODE_MEMO_SECTIONS: MemoSections = {
  schema_version: 1,
  company_snapshot: {
    bullets: [
      cite(
        "Axonode SA registered in Lausanne in May 2026 (Zefix CHE-214.882.331) — an EPFL-adjacent neuromorphic-computing venture.",
        ev("Axonode SA registered 2026-05-12, seat Lausanne.", AX_ZEFIX, "registry"),
      ),
      cite(
        "Two known members: Dr. Matteo Ricci (EPFL postdoc, neuromorphic inference) and Sofia Lindqvist (KTH, embedded flight systems).",
        ev("Ricci and Lindqvist listed as spikeflow maintainers.", AX_REPO, "github"),
      ),
      cite(
        "Product: an inference runtime and compiler that runs perception models on neuromorphic silicon aboard autonomous drones.",
        ev("spikeflow README: spiking runtime for sub-5W drone autonomy.", AX_REPO, "github"),
      ),
    ],
  },
  investment_hypotheses: {
    bullets: [
      cite(
        "On-board inference under 5 W is the unlock for beyond-line-of-sight drone autonomy — cloud round-trips are physically disqualifying.",
        ev("OEMs cite connectivity limits for BVLOS autonomy.", AX_PRESS, "press"),
      ),
      cite(
        "The defensible layer is the compiler and runtime above commodity neuromorphic chips, not the silicon itself.",
        ev("spikeflow targets three vendors' neuromorphic parts through one toolchain.", AX_REPO, "github"),
      ),
    ],
  },
  swot: {
    bullets: [
      cite(
        "Strength: 2,900-star runtime plus two paid OEM evaluations within a quarter of going public.",
        ev("2,900 stars on spikeflow.", AX_REPO, "github"),
        ev("Two European drone OEMs in paid evaluations (June 2026).", AX_PRESS, "press"),
      ),
      cite(
        "Weakness: the founders first worked together in April 2026 — three months of shared history.",
        ev("First co-commit on spikeflow dated 2026-04-08.", AX_REPO, "github"),
      ),
      cite(
        "Opportunity: European autonomy programs are funding on-board compute for inspection and delivery fleets.",
        ev("EU program call for low-power on-board autonomy compute.", AX_PRESS, "press"),
      ),
      cite(
        "Threat: neuromorphic chip vendors bundle their own SDKs and could absorb the toolchain layer.",
        ev("Vendor SDK bundling cited as the main competitive risk.", AX_PRESS, "press"),
      ),
    ],
  },
  team_and_history: {
    bullets: [
      cite(
        "Ricci: three first-author neuromorphic-inference papers and primary maintainer of spikeflow.",
        ev("First-author record on event-driven inference (2024–2026).", AX_OPENALEX, "openalex"),
        ev("Top committer on spikeflow.", AX_REPO, "github"),
      ),
      cite(
        "Lindqvist: shipped flight-controller firmware in two drone programs before joining; owns the embedded half of the stack.",
        ev("Lindqvist listed as embedded lead in release notes.", AX_REPO, "github"),
      ),
      cite(
        "Collaboration is young: no shared papers or repositories before April 2026.",
        ev("No co-authored works found for Ricci–Lindqvist before 2026.", AX_OPENALEX, "openalex"),
      ),
    ],
  },
  problem_and_product: {
    bullets: [
      cite(
        "Autonomy beyond line of sight fails on cloud latency and dead zones; regulators want deterministic on-board behavior.",
        ev("BVLOS certification requires on-board decision-making.", AX_PRESS, "press"),
      ),
      cite(
        "spikeflow compiles standard perception models to spiking hardware, cutting inference power roughly an order of magnitude in published benchmarks.",
        ev("Benchmark: ~10x energy reduction vs GPU baseline.", AX_PAPER, "arxiv"),
      ),
    ],
  },
  technology_and_defensibility: {
    bullets: [
      cite(
        "Compiler co-design with off-the-shelf neuromorphic silicon; the scheduling kernels are closed while the runtime API is open.",
        ev("Open runtime, closed scheduler split documented.", AX_REPO, "github"),
      ),
      cite(
        "Dependence on third-party silicon roadmaps is the structural risk — mitigated by supporting three vendors.",
        ev("Three supported chip targets as of v0.9.", AX_REPO, "github"),
      ),
    ],
  },
  market_tam_sam_som: {
    tam: "CHF 3.4B — edge-AI compute software for uncrewed systems (2030 projection)",
    sam: "CHF 620M — European drone OEMs and autonomy integrators",
    som: "CHF 55M — inspection and delivery fleets in DACH + Nordics, per-airframe licensing",
    assumptions: [
      "Per-airframe software licensing at CHF 400–900/yr depending on fleet size.",
      "European BVLOS approvals continue expanding through 2028.",
    ],
    bullets: [
      cite(
        "Edge-AI for uncrewed systems grows across inspection, delivery, and agriculture; software captures a rising share of airframe value.",
        ev("Edge autonomy spend forecast, June 2026.", AX_PRESS, "press"),
      ),
      cite(
        "Bottom-up serviceable estimate rests on per-airframe licensing across DACH and Nordic fleets.",
        ev("Fleet counts by segment, industry note.", AX_PRESS, "press"),
      ),
    ],
  },
  competition: {
    bullets: [
      cite(
        "Chip vendors' bundled SDKs are the incumbent path — deep on one chip, useless across vendors.",
        ev("Vendor SDKs cover single-chip targets only.", AX_PRESS, "press"),
      ),
      cite(
        "Drone OEM in-house autonomy teams optimize GPUs rather than neuromorphic parts — a power ceiling Axonode sidesteps.",
        ev("OEM stacks remain GPU-based in published teardowns.", AX_PRESS, "press"),
      ),
    ],
  },
  traction_and_kpis: {
    bullets: [
      cite(
        "2,900 GitHub stars and an active contributor base within four months of the public release.",
        ev("2,900 stars, 41 contributors on spikeflow.", AX_REPO, "github"),
      ),
      cite(
        "Two paid evaluation agreements with European drone OEMs referenced in the June press note.",
        ev("Two paid OEM evaluations announced.", AX_PRESS, "press"),
      ),
      gap("Recurring revenue beyond the paid evaluations is unverified.", "traction.revenue"),
    ],
  },
};

// ---------------------------------------------------------------------------
// TactiSense — public-data memo
// ---------------------------------------------------------------------------

const TS_REPO = "https://github.com/tactisense/skinprint";
const TS_PAPER = "https://arxiv.org/abs/2601.08832";
const TS_ZEFIX = "https://www.zefix.admin.ch/api/v1/company/uid/CHE-198.407.552";
const TS_PRESS = "https://alpentech-briefing.ch/2026/05/tactisense-printable-skins";
const TS_OPENALEX = "https://api.openalex.org/works/W4408233190";

export const TACTISENSE_MEMO_SECTIONS: MemoSections = {
  schema_version: 1,
  company_snapshot: {
    bullets: [
      cite(
        "TactiSense GmbH registered in Zurich in April 2026 (Zefix CHE-198.407.552), spun out of an ETH haptics lab.",
        ev("TactiSense GmbH registered 2026-04-03, seat Zurich.", TS_ZEFIX, "registry"),
      ),
      cite(
        "Founders Dr. Priya Nair and Jonas Wyss come from the same co-supervised ETH lab and have published together for three years.",
        ev("Nair–Wyss co-authorship record, 2023–2026.", TS_OPENALEX, "openalex"),
      ),
      cite(
        "Product: screen-printable capacitive skins that retrofit force and slip sensing onto existing robot grippers.",
        ev("skinprint README: printable tactile arrays for standard grippers.", TS_REPO, "github"),
      ),
    ],
  },
  investment_hypotheses: {
    bullets: [
      cite(
        "Force-blind grippers damage goods and cap picking speed; tactile retrofits are the cheapest fix for installed fleets.",
        ev("Integrators report damage rates on force-blind picking.", TS_PRESS, "press"),
      ),
      cite(
        "Printing sensors instead of assembling them collapses unit cost — the process know-how is the moat, not the sensor design.",
        ev("Screen-printing process described at device level only.", TS_PAPER, "arxiv"),
      ),
    ],
  },
  swot: {
    bullets: [
      cite(
        "Strength: three years of co-supervised lab collaboration between the founders — an unusually verified team signal.",
        ev("Four shared papers and a shared fabrication repo.", TS_OPENALEX, "openalex"),
      ),
      cite(
        "Weakness: traction is lab pilots, not deployments — no revenue signal in public data.",
        ev("Two gripper-maker lab pilots, no commercial terms disclosed.", TS_PRESS, "press"),
      ),
      cite(
        "Opportunity: e-commerce picking growth makes gentle handling a purchasing criterion.",
        ev("Damage-rate SLAs appearing in 3PL contracts.", TS_PRESS, "press"),
      ),
      cite(
        "Threat: gripper OEMs could integrate tactile sensing at the factory rather than as a retrofit.",
        ev("OEM-integrated sensing named as the main structural risk.", TS_PRESS, "press"),
      ),
    ],
  },
  team_and_history: {
    bullets: [
      cite(
        "Nair: PhD on printed capacitive arrays with six first-author papers; leads sensor design and calibration.",
        ev("First-author record on printed tactile sensing.", TS_OPENALEX, "openalex"),
      ),
      cite(
        "Wyss: built the lab's fabrication line; owns the printing process and yield engineering.",
        ev("Wyss maintains the fabrication tooling in skinprint.", TS_REPO, "github"),
      ),
      cite(
        "The pair share four papers and a fabrication repository across three years in the same co-supervised ETH lab.",
        ev("Nair–Wyss shared outputs, 2023–2026.", TS_OPENALEX, "openalex"),
      ),
    ],
  },
  problem_and_product: {
    bullets: [
      cite(
        "Grippers without touch crush produce, drop deformables, and run slow safety margins — measured cost, not anecdote.",
        ev("Damage and slowdown costs quantified by integrators.", TS_PRESS, "press"),
      ),
      cite(
        "TactiSense skins print onto flexible substrates and calibrate in software — retrofit in hours on standard parallel grippers.",
        ev("Retrofit procedure documented for two gripper families.", TS_REPO, "github"),
      ),
    ],
  },
  technology_and_defensibility: {
    bullets: [
      cite(
        "The published papers cover device physics; the printing process parameters and calibration dataset stay proprietary.",
        ev("Process windows withheld from publication.", TS_PAPER, "arxiv"),
      ),
      cite(
        "A calibration dataset across gripper geometries compounds with every retrofit — the data moat mirrors the hardware one.",
        ev("Calibration models per gripper family in skinprint.", TS_REPO, "github"),
      ),
    ],
  },
  market_tam_sam_som: {
    tam: "CHF 1.8B — robot end-effector sensing worldwide (2030 projection)",
    sam: "CHF 310M — European installed grippers eligible for tactile retrofit",
    som: null,
    assumptions: [
      "Retrofit pricing at CHF 1,200–2,400 per gripper plus a software subscription.",
      "Serviceable share limited to parallel-jaw fleets in the first two years.",
    ],
    bullets: [
      cite(
        "End-effector sensing grows with e-commerce picking; retrofits address the installed base OEM sensing cannot reach.",
        ev("Retrofit segment sizing, May 2026 industry note.", TS_PRESS, "press"),
      ),
      gap("Obtainable-share estimate needs pilot conversion data — SOM not yet computed.", "market.som"),
    ],
  },
  competition: {
    bullets: [
      cite(
        "Research-grade tactile sensors exist but cost hundreds of francs per fingertip — TactiSense competes on printable unit economics.",
        ev("Price comparison vs research-grade sensors.", TS_PRESS, "press"),
      ),
      cite(
        "Gripper OEMs ship force-torque options at the wrist, not the finger surface — complementary today, competitive if they move down.",
        ev("Wrist-mounted sensing positioned as the OEM default.", TS_PRESS, "press"),
      ),
    ],
  },
  traction_and_kpis: {
    bullets: [
      cite(
        "Lab pilots with two European gripper makers; 340 stars on the calibration tooling repo.",
        ev("Two lab pilots; 340 stars on skinprint.", TS_REPO, "github"),
      ),
      gap("Revenue and commercial pilot terms unverified from public data.", "traction.revenue"),
    ],
  },
};
