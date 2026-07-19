/**
 * Admin data layer: read-only joins over the contract fixtures (silver/gold
 * mirrors in @/mocks/fixtures/generated) plus the LIVE demo store
 * (@/mocks/state) so venture/outreach/interview facts stay in sync with the
 * rest of the demo. Everything is defensive, fixture rows are treated as
 * Record<string, unknown>.
 */
import { useSyncExternalStore } from "react";
import * as GEN from "@/mocks/fixtures/generated";
import { getDB, getVersion, subscribe, type MockDB } from "@/mocks/state";
import type { OutreachRow } from "@/lib/domain/types";

export type Raw = Record<string, unknown>;

// --- live store subscription -----------------------------------------------

/** Re-renders on every store mutation; read state via getDB(). */
export function useLiveVersion(): number {
  return useSyncExternalStore(subscribe, getVersion, getVersion);
}

export { getDB };
export type { MockDB };

// --- defensive field access -------------------------------------------------

export function str(v: unknown): string | null {
  return typeof v === "string" && v.length > 0 ? v : null;
}

export function num(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

export function arr(v: unknown): unknown[] {
  return Array.isArray(v) ? v : [];
}

export function fmtConfidence(v: unknown): string {
  const n = num(v);
  return n == null ? "-" : n.toFixed(2);
}

export function fmtDate(v: unknown): string {
  const s = str(v);
  if (!s) return "-";
  return s.slice(0, 10);
}

// --- table registry (the browsable database) --------------------------------

export type Layer = "silver" | "gold" | "ops";

export interface TableDef {
  key: string;
  label: string;
  layer: Layer;
  rows: Raw[];
}

const T = (key: string, label: string, layer: Layer, rows: unknown[]): TableDef => ({
  key,
  label,
  layer,
  rows: rows as Raw[],
});

/** Static fixture tables in medallion order. Rebuilt cheaply; rows are shared refs. */
export function fixtureTables(): TableDef[] {
  return [
    // silver, resolved entities and signals
    T("persons", "persons", "silver", GEN.persons),
    T("personSourceRecords", "person_source_records", "silver", GEN.personSourceRecords),
    T("personSourceLinks", "person_source_links", "silver", GEN.personSourceLinks),
    T("personConnections", "person_connections", "silver", GEN.personConnections),
    T("publications", "publications", "silver", GEN.publications),
    T("projects", "projects", "silver", GEN.projects),
    T("companies", "companies", "silver", GEN.companies),
    T("authorships", "authorships", "silver", GEN.authorships),
    T("contributions", "contributions", "silver", GEN.contributions),
    T("officers", "officers", "silver", GEN.officers),
    T("personFeatures", "person_features", "silver", GEN.personFeatures),
    // gold, the investable views
    T("ventures", "ventures", "gold", GEN.ventures),
    T("ventureMembers", "venture_members", "gold", GEN.ventureMembers),
    T("ventureScores", "venture_scores", "gold", GEN.ventureScores),
    T("theses", "theses", "gold", GEN.theses),
    T("scoreWeights", "score_weights", "gold", GEN.scoreWeights),
    T("idealCandidates", "ideal_candidates", "gold", GEN.idealCandidates),
    T("candidatePool", "candidate_pool", "gold", GEN.candidatePool),
    T("ventureGaps", "venture_gaps", "gold", GEN.ventureGaps),
    T("memos", "memos", "gold", GEN.memos),
    T("outreach", "outreach", "gold", GEN.outreach),
    T("interviews", "interviews", "gold", GEN.interviews),
    // ops
    T("erReviewQueue", "er_review_queue", "ops", GEN.erReviewQueue),
  ];
}

// --- overview stats ---------------------------------------------------------

export interface StatCard {
  label: string;
  count: number;
  /** Where the number comes from, the admin is the provenance story. */
  source: "fixture" | "live";
}

export interface LayerStats {
  layer: Layer;
  eyebrow: string;
  caption: string;
  cards: StatCard[];
}

export function buildLayerStats(db: MockDB): LayerStats[] {
  const silver: StatCard[] = [
    { label: "persons", count: GEN.persons.length, source: "fixture" },
    { label: "source records", count: GEN.personSourceRecords.length, source: "fixture" },
    { label: "source links", count: GEN.personSourceLinks.length, source: "fixture" },
    { label: "connections", count: GEN.personConnections.length, source: "fixture" },
    { label: "publications", count: GEN.publications.length, source: "fixture" },
    { label: "projects", count: GEN.projects.length, source: "fixture" },
    { label: "companies", count: GEN.companies.length, source: "fixture" },
    { label: "authorships", count: GEN.authorships.length, source: "fixture" },
    { label: "contributions", count: GEN.contributions.length, source: "fixture" },
    { label: "officers", count: GEN.officers.length, source: "fixture" },
  ];

  const scoreCount = Object.values(db.scoreHistory).reduce((n, list) => n + list.length, 0);
  const gapCount = Object.values(db.gaps).reduce((n, list) => n + list.length, 0);
  const gold: StatCard[] = [
    { label: "ventures", count: db.ventures.length, source: "live" },
    { label: "scores", count: scoreCount, source: "live" },
    { label: "memos", count: Object.keys(db.memos).length, source: "live" },
    { label: "outreach", count: db.outreach.length, source: "live" },
    { label: "interviews", count: GEN.interviews.length, source: "fixture" },
    { label: "gaps", count: gapCount, source: "live" },
  ];

  const ops: StatCard[] = [
    { label: "er review queue", count: GEN.erReviewQueue.length, source: "fixture" },
  ];

  return [
    {
      layer: "silver",
      eyebrow: "Silver",
      caption: "resolved entities + signal tables",
      cards: silver,
    },
    { layer: "gold", eyebrow: "Gold", caption: "investable views served to the app", cards: gold },
    { layer: "ops", eyebrow: "Ops", caption: "human-in-the-loop review", cards: ops },
  ];
}

// --- ER health (links by match_method) --------------------------------------

export interface ErMethodStat {
  method: string;
  kind: string;
  links: number;
  avgConfidence: number;
  active: number;
  retracted: number;
}

function methodKind(method: string): string {
  if (method.startsWith("det_")) return "deterministic";
  if (method === "splink") return "probabilistic";
  if (method === "llm_adjudication") return "llm";
  if (method === "human_review") return "human";
  return "seed";
}

export interface ErHealth {
  methods: ErMethodStat[];
  totalLinks: number;
  totalActive: number;
  totalRetracted: number;
  avgConfidence: number;
}

export function buildErHealth(): ErHealth {
  const byMethod = new Map<string, { conf: number[]; active: number; retracted: number }>();
  const links = GEN.personSourceLinks as Raw[];
  for (const link of links) {
    const method = str(link.match_method) ?? "unknown";
    const entry = byMethod.get(method) ?? { conf: [], active: 0, retracted: 0 };
    const c = num(link.match_confidence);
    if (c != null) entry.conf.push(c);
    if (str(link.status) === "retracted") entry.retracted += 1;
    else entry.active += 1;
    byMethod.set(method, entry);
  }
  const methods: ErMethodStat[] = [...byMethod.entries()]
    .map(([method, e]) => ({
      method,
      kind: methodKind(method),
      links: e.active + e.retracted,
      avgConfidence: e.conf.length ? e.conf.reduce((a, b) => a + b, 0) / e.conf.length : 0,
      active: e.active,
      retracted: e.retracted,
    }))
    .sort((a, b) => b.links - a.links || a.method.localeCompare(b.method));
  const totalActive = methods.reduce((n, m) => n + m.active, 0);
  const totalRetracted = methods.reduce((n, m) => n + m.retracted, 0);
  const allConf = links.map((l) => num(l.match_confidence)).filter((c): c is number => c != null);
  return {
    methods,
    totalLinks: links.length,
    totalActive,
    totalRetracted,
    avgConfidence: allConf.length ? allConf.reduce((a, b) => a + b, 0) / allConf.length : 0,
  };
}

// --- person dossier (the detail-panel join) ---------------------------------

export interface SourceRecordEntry {
  link: Raw;
  record: Raw | null;
}

export interface SourceGroup {
  source: string;
  entries: SourceRecordEntry[];
}

export interface PersonMembership {
  ventureId: string;
  name: string;
  oneLiner: string | null;
  roleHint: string | null;
  isFounderGuess: boolean;
  finalScore: number | null;
  status: string | null;
}

export interface PersonConnectionFact {
  otherId: string;
  otherName: string;
  types: string[];
  weight: number;
}

export interface PersonDossier {
  person: Raw;
  quality: number | null;
  activeBySource: SourceGroup[];
  retracted: SourceRecordEntry[];
  code: { contribution: Raw; project: Raw | null }[];
  research: { authorship: Raw; publication: Raw | null }[];
  companies: { officer: Raw; company: Raw | null }[];
  memberships: PersonMembership[];
  outreach: OutreachRow[];
  /** Fixture gold.interview rows for this person. */
  interviews: Raw[];
  /** Live interview stage when this person is the demo outreach target. */
  liveInterviewStage: string | null;
  features: Record<string, number> | null;
  connections: PersonConnectionFact[];
}

const recordById = new Map<string, Raw>(
  (GEN.personSourceRecords as Raw[]).map((r) => [String(r.source_record_id), r]),
);
const projectById = new Map<string, Raw>(
  (GEN.projects as Raw[]).map((r) => [String(r.project_id), r]),
);
const publicationById = new Map<string, Raw>(
  (GEN.publications as Raw[]).map((r) => [String(r.publication_id), r]),
);
const companyById = new Map<string, Raw>(
  (GEN.companies as Raw[]).map((r) => [String(r.company_id), r]),
);
export const personById = new Map<string, Raw>(
  (GEN.persons as Raw[]).map((r) => [String(r.person_id), r]),
);

export function buildPersonDossier(personId: string, db: MockDB): PersonDossier | null {
  const person = personById.get(personId);
  if (!person) return null;

  const links = (GEN.personSourceLinks as Raw[]).filter((l) => l.person_id === personId);
  const active = links.filter((l) => str(l.status) !== "retracted");
  const retractedLinks = links.filter((l) => str(l.status) === "retracted");

  const groups = new Map<string, SourceRecordEntry[]>();
  for (const link of active) {
    const record = recordById.get(String(link.source_record_id)) ?? null;
    const source = record ? (str(record.source) ?? "unknown") : "unknown";
    const list = groups.get(source) ?? [];
    list.push({ link, record });
    groups.set(source, list);
  }
  const activeBySource: SourceGroup[] = [...groups.entries()]
    .map(([source, entries]) => ({ source, entries }))
    .sort((a, b) => b.entries.length - a.entries.length || a.source.localeCompare(b.source));

  const retracted: SourceRecordEntry[] = retractedLinks.map((link) => ({
    link,
    record: recordById.get(String(link.source_record_id)) ?? null,
  }));

  const code = (GEN.contributions as Raw[])
    .filter((c) => c.person_id === personId)
    .map((contribution) => ({
      contribution,
      project: projectById.get(String(contribution.project_id)) ?? null,
    }));

  const research = (GEN.authorships as Raw[])
    .filter((a) => a.person_id === personId)
    .map((authorship) => ({
      authorship,
      publication: publicationById.get(String(authorship.publication_id)) ?? null,
    }));

  const companies = (GEN.officers as Raw[])
    .filter((o) => o.person_id === personId)
    .map((officer) => ({
      officer,
      company: companyById.get(String(officer.company_id)) ?? null,
    }));

  const memberships: PersonMembership[] = [];
  for (const venture of db.ventures) {
    const members = db.team[venture.venture_id] ?? [];
    const membership = members.find((m) => m.person_id === personId);
    if (!membership) continue;
    memberships.push({
      ventureId: venture.venture_id,
      name: venture.name,
      oneLiner: venture.one_liner ?? null,
      roleHint: membership.role_hint,
      isFounderGuess: membership.is_founder_guess,
      finalScore: venture.final_score,
      status: venture.status,
    });
  }

  const outreach = db.outreach.filter((o) => o.person_id === personId);
  const interviews = (GEN.interviews as Raw[]).filter((i) => i.person_id === personId);
  const liveInterviewStage = outreach.length > 0 ? db.interview.stage : null;

  const featureRow = (GEN.personFeatures as Raw[]).find((f) => f.person_id === personId);
  let features: Record<string, number> | null = null;
  if (featureRow && featureRow.features && typeof featureRow.features === "object") {
    features = {};
    for (const [k, v] of Object.entries(featureRow.features as Raw)) {
      const n = num(v);
      if (n != null) features[k] = n;
    }
  }

  const connections: PersonConnectionFact[] = [];
  const byOther = new Map<string, PersonConnectionFact>();
  for (const conn of GEN.personConnections as Raw[]) {
    const a = String(conn.person_a_id);
    const b = String(conn.person_b_id);
    if (a !== personId && b !== personId) continue;
    const otherId = a === personId ? b : a;
    const other = personById.get(otherId);
    const fact = byOther.get(otherId) ?? {
      otherId,
      otherName: other ? (str(other.full_name) ?? otherId) : otherId,
      types: [],
      weight: 0,
    };
    const type = str(conn.connection_type);
    if (type && !fact.types.includes(type)) fact.types.push(type);
    fact.weight += num(conn.weight) ?? 0;
    byOther.set(otherId, fact);
  }
  connections.push(...byOther.values());

  return {
    person,
    quality: num(person.data_quality_score),
    activeBySource,
    retracted,
    code,
    research,
    companies,
    memberships,
    outreach,
    interviews,
    liveInterviewStage,
    features,
    connections,
  };
}
