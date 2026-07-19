/**
 * The scripted AI interview between the interviewer and Lena Fischer.
 * Each turn: the AI message, the founder's (auto-typed in autopilot) reply,
 * and which memo gap the answer fills. Streaming timing is derived
 * deterministically per-message in MockDataSource.
 *
 * TODO(Track A): replace with the full 10-turn script from the demo plan.
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
    ai: "That's everything, Lena. Your answers — with your consent on record — go into the fund's memo now; a partner reviews the update this week and you'll hear directly either way. Thank you.",
    founder: null,
  },
];
