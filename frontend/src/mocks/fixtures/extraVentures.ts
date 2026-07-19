/**
 * The 9 hand-authored ventures that join GraspLab in the ranked list, plus
 * their teams/gaps/memos where the demo needs them. All fictional Swiss
 * deep-tech flavored companies; category scores must satisfy
 * rerank.computeFinalScore arithmetic (the client recomputes finals live).
 *
 * TODO(Track A): author the full dataset per the demo plan (Axonode 76.3 #1,
 * TactiSense, FastSim, Wayline, Ceresbot, Périsurg, CairnSight, Loopwise,
 * Otterix `needs_more_data`).
 */
import type { Memo, RankedVenture, VentureGap, VentureTeamMember } from "@/lib/domain/types";

export const EXTRA_VENTURES: RankedVenture[] = [];

export const EXTRA_TEAM: Record<string, VentureTeamMember[]> = {};

export const EXTRA_GAPS: Record<string, VentureGap[]> = {};

export const EXTRA_MEMOS: Record<string, Memo> = {};
