/**
 * Graph model for the admin people graph: person nodes (silver.persons),
 * venture nodes (live store), person–person edges (silver.person_connections,
 * aggregated per pair) and dashed membership edges (live team map).
 * Initial positions are seeded from index angles so the settled layout is
 * deterministic-ish run to run.
 */
import type { SimulationLinkDatum, SimulationNodeDatum } from "d3-force";
import * as GEN from "@/mocks/fixtures/generated";
import { num, str, type MockDB, type Raw } from "./data";

export const GRAPH_W = 760;
export const GRAPH_H = 600;

export interface PersonNode extends SimulationNodeDatum {
  kind: "person";
  id: string;
  name: string;
  initials: string;
  quality: number;
  degree: number;
  r: number;
}

export interface VentureNode extends SimulationNodeDatum {
  kind: "venture";
  id: string;
  name: string;
  /** Half the square's side length. */
  half: number;
  finalScore: number | null;
  status: string | null;
}

export type GraphNode = PersonNode | VentureNode;

export interface GraphEdge extends SimulationLinkDatum<GraphNode> {
  id: string;
  kind: "connection" | "membership";
  sourceId: string;
  targetId: string;
  weight: number;
  label: string;
}

export interface GraphModel {
  nodes: GraphNode[];
  edges: GraphEdge[];
  /** node id -> ids of adjacent nodes (for hover darkening). */
  neighbors: Map<string, Set<string>>;
  /**
   * Ventures kept off the canvas because none of their gold.venture_members
   * resolve to a silver.persons row — an ER coverage gap worth naming.
   */
  unresolvedVentures: string[];
  /** Persons with no connection and no venture membership. */
  isolatedPersons: number;
}

function initialsOf(name: string): string {
  const parts = name.split(/\s+/).filter(Boolean);
  const first = parts[0]?.[0] ?? "?";
  const last = parts.length > 1 ? (parts[parts.length - 1][0] ?? "") : "";
  return (first + last).toUpperCase();
}

export function nodeHitRadius(node: GraphNode): number {
  return node.kind === "person" ? node.r : node.half * Math.SQRT2;
}

export function buildGraphModel(db: MockDB): GraphModel {
  const persons = GEN.persons as Raw[];

  // Aggregate the (sparse) person–person connection rows per unordered pair.
  const pairAgg = new Map<string, { a: string; b: string; weight: number; types: string[] }>();
  for (const conn of GEN.personConnections as Raw[]) {
    const a = str(conn.person_a_id);
    const b = str(conn.person_b_id);
    if (!a || !b) continue;
    const key = a < b ? `${a}|${b}` : `${b}|${a}`;
    const agg = pairAgg.get(key) ?? { a, b, weight: 0, types: [] };
    agg.weight += num(conn.weight) ?? 1;
    const type = str(conn.connection_type);
    if (type && !agg.types.includes(type)) agg.types.push(type);
    pairAgg.set(key, agg);
  }

  // Degree = aggregated connections + venture memberships.
  const degree = new Map<string, number>();
  const bump = (id: string) => degree.set(id, (degree.get(id) ?? 0) + 1);
  for (const agg of pairAgg.values()) {
    bump(agg.a);
    bump(agg.b);
  }
  const personIds = new Set(persons.map((p) => String(p.person_id)));
  const memberships: { ventureId: string; personId: string; role: string | null }[] = [];
  const resolvedVentures = new Set<string>();
  const unresolvedVentures: string[] = [];
  for (const venture of db.ventures) {
    let resolved = 0;
    for (const member of db.team[venture.venture_id] ?? []) {
      // Team rows whose person_id has no silver.persons row can't be drawn.
      if (!personIds.has(member.person_id)) continue;
      resolved += 1;
      memberships.push({
        ventureId: venture.venture_id,
        personId: member.person_id,
        role: member.role_hint,
      });
      bump(member.person_id);
    }
    if (resolved > 0) resolvedVentures.add(venture.venture_id);
    else unresolvedVentures.push(venture.name);
  }

  const cx = GRAPH_W / 2;
  const cy = GRAPH_H / 2;

  const personNodes: PersonNode[] = persons.map((p, i) => {
    const id = String(p.person_id);
    const name = str(p.full_name) ?? id.slice(0, 8);
    const quality = num(p.data_quality_score) ?? 0.5;
    const deg = degree.get(id) ?? 0;
    const angle = (i / Math.max(persons.length, 1)) * Math.PI * 2 - Math.PI / 2;
    return {
      kind: "person",
      id,
      name,
      initials: initialsOf(name),
      quality,
      degree: deg,
      r: Math.min(18, Math.max(10, 10 + deg * 2 + quality * 4)),
      x: cx + Math.cos(angle) * 210,
      y: cy + Math.sin(angle) * 170,
    };
  });

  const drawnVentures = db.ventures.filter((v) => resolvedVentures.has(v.venture_id));
  const ventureNodes: VentureNode[] = drawnVentures.map((v, i) => {
    const angle = (i / Math.max(drawnVentures.length, 1)) * Math.PI * 2 + Math.PI / 4;
    return {
      kind: "venture",
      id: v.venture_id,
      name: v.name,
      half: 13,
      finalScore: v.final_score ?? null,
      status: v.status ?? null,
      x: cx + Math.cos(angle) * 90,
      y: cy + Math.sin(angle) * 70,
    };
  });

  const nodes: GraphNode[] = [...personNodes, ...ventureNodes];
  const nodeIds = new Set(nodes.map((n) => n.id));

  const edges: GraphEdge[] = [];
  for (const agg of pairAgg.values()) {
    if (!nodeIds.has(agg.a) || !nodeIds.has(agg.b)) continue;
    edges.push({
      id: `conn:${agg.a}:${agg.b}`,
      kind: "connection",
      source: agg.a,
      target: agg.b,
      sourceId: agg.a,
      targetId: agg.b,
      weight: agg.weight,
      label: agg.types.join(" + "),
    });
  }
  for (const m of memberships) {
    if (!nodeIds.has(m.ventureId)) continue;
    edges.push({
      id: `member:${m.ventureId}:${m.personId}`,
      kind: "membership",
      source: m.ventureId,
      target: m.personId,
      sourceId: m.ventureId,
      targetId: m.personId,
      weight: 1,
      label: m.role ?? "member",
    });
  }

  const neighbors = new Map<string, Set<string>>();
  const connect = (a: string, b: string) => {
    const set = neighbors.get(a) ?? new Set<string>();
    set.add(b);
    neighbors.set(a, set);
  };
  for (const e of edges) {
    connect(e.sourceId, e.targetId);
    connect(e.targetId, e.sourceId);
  }

  const isolatedPersons = personNodes.filter((n) => !neighbors.has(n.id)).length;

  return { nodes, edges, neighbors, unresolvedVentures, isolatedPersons };
}
