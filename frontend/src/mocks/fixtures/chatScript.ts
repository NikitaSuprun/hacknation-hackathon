/**
 * The scripted AI interview between the interviewer and Lena Fischer.
 * Each turn: the AI message, the founder's (auto-typed in autopilot) reply,
 * and which memo gap the answer fills. Streaming timing is derived
 * deterministically per-message in MockDataSource.
 *
 * Tone contract: warm, precise, consent-first, and never the language of an
 * application process (no "apply", "submit"). No em dashes anywhere; a copy
 * audit test enforces both.
 */

export interface ScriptedTurn {
  /** What the AI interviewer says (streamed token-by-token). */
  ai: string;
  /** Lena's reply. Null on the closing turn. */
  founder: string | null;
  /** gap fields this answer fills (drives the re-score beat). */
  fills?: string[];
}

export const INTERVIEW_SCRIPT: ScriptedTurn[] = [
  {
    ai: "Hi Lena, thanks for making time and for giving your consent. I'm the interview assistant for the fund reviewing GraspLab. This takes about ten minutes. You can type skip on anything, and nothing here is a commitment in either direction. Ready?",
    founder: "Ready, go ahead.",
  },
  {
    ai: "First, the thing our public data can't see: do you have paying pilots or revenue today?",
    founder:
      "Yes. Three paid pilots, all in warehouse logistics, running since spring. Each pays CHF 4,000 a month, so about CHF 12k MRR. Our lead pilot is at 96.3% pick accuracy, and two of the three will decide whether to convert in December.",
    fills: ["traction.revenue"],
  },
  {
    ai: "That's concrete, thank you. Which customer segment do you serve first, and roughly how large is it?",
    founder:
      "Mid-size 3PL warehouses in the DACH region, roughly 1,900 sites. At about CHF 60k per site per year, that's a serviceable market of around CHF 115M before the rest of Europe.",
    fills: ["market.tam"],
  },
  {
    ai: "On the team: are you and Wei both full-time on GraspLab?",
    founder:
      "I've been full-time since June. Wei defends his PhD in August and joins full-time on September 1. He already holds founder equity.",
    fills: ["team.commitment"],
  },
  {
    ai: "How is the ETH research IP licensed to the company?",
    founder:
      "Exclusive licence, signed June 28, standard spin-off terms. The model weights and the training pipeline are ours outright.",
    fills: ["tech.ip_licensing"],
  },
  {
    ai: "Our records show no prior venture funding. Is that right, and how long is your runway?",
    founder:
      "Correct, no equity raised. We run on a CHF 150k research grant plus the pilot fees, burn about CHF 14k a month, and have roughly 11 months of runway.",
    fills: ["funding.history_verified"],
  },
  {
    ai: "Last one: what does the public data get wrong about GraspLab?",
    founder:
      "The star spike came from one viral benchmark post. Stars aren't users, so I'd discount them. The number I'd watch is our 41-company design-partner waitlist.",
  },
  {
    ai: "That's everything, Lena. Thank you. Your answers now go into the fund's memo, with your consent on record. A partner reviews the update this week, and you'll hear either way. To be clear, this review is never a promise of investment. Take care.",
    founder: null,
  },
];

/**
 * The scripted founder reply to an investor follow-up question on the
 * completed interview (streamed on the venture page).
 */
export const FOLLOW_UP_REPLY =
  "Both December decisions are on the calendar: one on the 9th and one on the 16th. The conversion terms are a 12-month order at CHF 60k per site with a 30-day out. If either converts, we will share the signed order that same week.";
