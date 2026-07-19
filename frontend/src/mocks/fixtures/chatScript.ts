/**
 * The scripted AI interview between the interviewer and Lena Fischer.
 * Each turn: the AI message, the founder's (auto-typed in autopilot) reply,
 * and which memo gap the answer fills. Streaming timing is derived
 * deterministically per-message in MockDataSource.
 *
 * Tone contract: warm, precise, consent-first — and never the language of
 * an application process (no "apply", "submit"; a copy-audit test enforces it).
 */

export interface ScriptedTurn {
  /** What the AI interviewer says (streamed token-by-token). */
  ai: string;
  /** Lena's reply — null on the closing turn. */
  founder: string | null;
  /** gap fields this answer fills (drives the re-score beat). */
  fills?: string[];
}

export const INTERVIEW_SCRIPT: ScriptedTurn[] = [
  {
    ai: "Hi Lena — thanks for making time, and for your consent just now. I'm the interview assistant for the fund reviewing GraspLab. This takes about 15 minutes, you can type skip on anything, and nothing here is a commitment in either direction. Ready?",
    founder: "Ready — go ahead.",
  },
  {
    ai: "Great. First, the thing our public data can't see: do you have paying pilots or revenue today?",
    founder:
      "Yes — three paid pilots, all warehouse logistics. They started between April and June. Each pays CHF 4,000 a month as a pilot fee, so about CHF 12k MRR.",
    fills: ["traction.revenue"],
  },
  {
    ai: "That's helpful, thank you. How are the pilots performing, and when do they decide about converting?",
    founder:
      "We hold ourselves to at least 95% pick accuracy on a 500-SKU test set before we invoice. The lead pilot sits at 96.3% today, and two of the three have conversion decisions scheduled for December.",
  },
  {
    ai: "Which customer segment do you serve first, and roughly how large is it?",
    founder:
      "Mid-size 3PL warehouses in DACH — roughly 1,900 sites. At about CHF 60k per site per year, that's around CHF 115M serviceable before we look at the rest of Europe.",
    fills: ["market.tam"],
  },
  {
    ai: "On the team — are you and Wei both full-time on GraspLab?",
    founder:
      "I've been full-time since June. Wei defends his PhD in August and has signed to join full-time on September 1 — he already holds founder equity.",
    fills: ["team.commitment"],
  },
  {
    ai: "Noted, thank you. How is the ETH research IP licensed to the company?",
    founder:
      "We signed an exclusive licence with ETH transfer on June 28 — standard spin-off terms with a small royalty on product revenue. The model weights and the training pipeline are ours outright.",
    fills: ["tech.ip_licensing"],
  },
  {
    ai: "Our records show no prior venture funding for GraspLab — is that right?",
    founder:
      "Correct — no equity funding of any kind. We run on a CHF 150k non-dilutive research grant plus the pilot fees.",
    fills: ["funding.history_verified"],
  },
  {
    ai: "How long does your current runway last at today's burn?",
    founder:
      "Burn is about CHF 14k a month, mostly cloud training. With the grant and pilot fees, that gives us roughly 11 months. We're planning a CHF 750k pre-seed this autumn.",
  },
  {
    ai: "Almost done. In your view, what does the public data get wrong about GraspLab?",
    founder:
      "The star spike came from one viral benchmark post — stars aren't users, and I'd discount them. The number I'd watch instead is our 41-company design-partner waitlist, which we've never announced.",
  },
  {
    ai: "That's everything, Lena — thank you. Your answers, with your consent on record, go into the fund's memo now. A partner reviews the update this week and you'll hear directly either way. You can review or withdraw your data at any time via the data-rights link in your invitation. To be clear, this review is never a promise of investment. Take care.",
    founder: null,
  },
];
