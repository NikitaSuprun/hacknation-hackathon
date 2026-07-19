/**
 * Client-side venture query engine: structured filters plus a deterministic,
 * dependency-free "semantic-ish" text scorer over the ranked pool.
 *
 * Honest scope note: this demos the query UX over the ~11-row demo pool (and
 * the live-mode fetched ranking, which reuses the same code). The production
 * embedding search runs in-warehouse later; nothing here pretends otherwise.
 *
 * Scoring formula (all pure, no deps):
 *   1. Build a per-venture document from name, one_liner, market_tags, every
 *      category rationale, every evidence claim/snippet.
 *   2. Normalize tokens: lowercase + diacritic fold + camelCase split + basic
 *      suffix stemming (plural / -ing / -ed trim), stopwords dropped.
 *   3. Map tokens through a small domain synonym table to canonical concepts
 *      (robot/arm/manipulator..., touch/tactile/sensing..., see SYNONYM_GROUPS).
 *   4. Per unique query concept: sum field weights where it appears
 *      (name x3, tags x2.5, one_liner x2, rationales x1, evidence x0.75),
 *      capped at PER_TOKEN_CAP per token.
 *   5. Bigram bonus: +BIGRAM_BONUS per adjacent query pair found adjacent
 *      (modulo stopwords) in any field.
 *   6. relevance = raw / maxPossible, clamped to 0..1 (deterministic).
 */

import type { RankedVenture, VentureStatus } from "@/lib/domain/types";

// ---------------------------------------------------------------------------
// Public types
// ---------------------------------------------------------------------------

export type TierFilter = "scored" | "needs_more_data" | "untiered";

export interface VentureQuery {
  /** Free prompt; "" = no text scoring. */
  text: string;
  /** Must intersect market_tags (empty = any). Case-insensitive. */
  sectors: string[];
  /** Matches locationOf(v)?.city (empty = any). Case-insensitive. */
  locations: string[];
  /** final_score floor (null = no floor). */
  minScore: number | null;
  /** Empty = any. */
  statuses: VentureStatus[];
  /** Empty = any; "untiered" selects quality_tier === null. */
  tiers: TierFilter[];
}

export interface MatchedSnippet {
  /** "name" | "one_liner" | "tags" | "rationale:<category>" | "evidence:<category>". */
  field: string;
  /** Sentence fragment around the match, <= 90 chars (incl. ellipses). */
  snippet: string;
  /** [start, end) offsets of matched tokens within `snippet` for <mark> highlighting. */
  ranges: [number, number][];
}

export interface QueryHit {
  venture: RankedVenture;
  /** 0..1 when the query has text; null when text is empty (ranking order kept). */
  relevance: number | null;
  /** Up to 3 best snippets for UI highlighting (empty when relevance is null). */
  matched: MatchedSnippet[];
  city: string | null;
}

export interface LocationGuess {
  city: string;
  confidence: "explicit" | "inferred";
}

// ---------------------------------------------------------------------------
// Query construction helpers
// ---------------------------------------------------------------------------

export function emptyQuery(): VentureQuery {
  return { text: "", sectors: [], locations: [], minScore: null, statuses: [], tiers: [] };
}

export function isEmptyQuery(q: VentureQuery): boolean {
  return (
    q.text.trim() === "" &&
    q.sectors.length === 0 &&
    q.locations.length === 0 &&
    q.minScore == null &&
    q.statuses.length === 0 &&
    q.tiers.length === 0
  );
}

/** Number of active constraints (free text counts as one). Drives the Clear button. */
export function countActiveFilters(q: VentureQuery): number {
  return (
    (q.text.trim() ? 1 : 0) +
    q.sectors.length +
    q.locations.length +
    (q.minScore != null ? 1 : 0) +
    q.statuses.length +
    q.tiers.length
  );
}

// ---------------------------------------------------------------------------
// Tokenization: fold, split, stem, synonyms
// ---------------------------------------------------------------------------

/** Lowercase + strip diacritics (Zürich -> zurich, Genève -> geneve). */
function fold(s: string): string {
  return s
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
}

/** Basic suffix trim — deliberately crude but deterministic. */
function stem(t: string): string {
  if (t.length > 4 && t.endsWith("ies")) return t.slice(0, -3) + "y";
  if (t.length > 4 && t.endsWith("ing")) return t.slice(0, -3);
  if (t.length > 3 && t.endsWith("ed") && !t.endsWith("eed")) return t.slice(0, -2);
  if (
    t.length > 3 &&
    t.endsWith("s") &&
    !t.endsWith("ss") &&
    !t.endsWith("us") &&
    !t.endsWith("is")
  ) {
    return t.slice(0, -1);
  }
  return t;
}

/**
 * Domain synonym table. Each group collapses to the first entry (canonical).
 * Keys are stemmed at build time so surface forms ("sensing", "robotics") land
 * in the same bucket as their group words.
 */
const SYNONYM_GROUPS: string[][] = [
  ["robot", "robotic", "robotics", "arm", "arms", "manipulator", "manipulation", "cobot"],
  ["tactile", "touch", "sensing", "sensor", "sense", "haptic", "haptics", "skin", "skins"],
  ["warehouse", "logistics", "3pl", "fulfilment", "fulfillment", "intralogistics", "amr"],
  ["grasp", "grasping", "gripper", "gripping", "pick", "picking"],
  ["vision", "camera", "perception", "imaging", "optical"],
  ["drone", "uav", "uas", "aerial", "quadrotor"],
  ["simulation", "sim", "simulator", "physics"],
  ["voice", "speech", "spoken", "multilingual", "asr", "tts"],
  ["agent", "agents", "assistant", "copilot", "chatbot"],
  ["surgical", "surgery", "medical", "medtech", "endovascular", "clinical", "catheter"],
  ["agri", "agriculture", "agtech", "farm", "farming", "weeding", "weed", "crop", "crops"],
  ["slam", "mapping", "map", "maps", "localization", "localisation", "odometry", "navigation"],
  ["neuromorphic", "spiking"],
  ["inspection", "inspect", "monitoring", "survey", "surveying"],
  ["alpine", "mountain", "glacier"],
];

const SYNONYM_MAP: Map<string, string> = (() => {
  const m = new Map<string, string>();
  for (const group of SYNONYM_GROUPS) {
    const canonical = stem(fold(group[0]));
    for (const word of group) m.set(stem(fold(word)), canonical);
  }
  return m;
})();

const STOPWORDS = new Set([
  "a", "an", "the", "and", "or", "of", "for", "in", "on", "at", "to", "with",
  "by", "from", "into", "over", "under", "is", "are", "was", "were", "be",
  "been", "being", "that", "this", "these", "those", "it", "its", "as", "we",
  "our", "they", "their", "you", "your", "i", "im", "eg", "ie", "what",
  "which", "who", "whose", "how", "when", "where", "also", "via", "per", "vs",
  "about", "around", "near", "based",
]);

interface Tok {
  /** Canonical concept (folded + stemmed + synonym-collapsed). */
  canon: string;
  /** Offsets into the ORIGINAL field text (for snippet highlighting). */
  start: number;
  end: number;
}

const isUpper = (c: string) => c !== c.toLowerCase() && c === c.toUpperCase();
const isLower = (c: string) => c !== c.toUpperCase() && c === c.toLowerCase();

/** Split a word at camelCase boundaries ("TactiSense" -> "Tacti","Sense"). */
function camelPieces(word: string, offset: number): { piece: string; start: number }[] {
  const out: { piece: string; start: number }[] = [];
  let start = 0;
  for (let i = 1; i < word.length; i++) {
    const boundary =
      (isLower(word[i - 1]) && isUpper(word[i])) ||
      (isUpper(word[i - 1]) && isUpper(word[i]) && i + 1 < word.length && isLower(word[i + 1]));
    if (boundary) {
      out.push({ piece: word.slice(start, i), start: offset + start });
      start = i;
    }
  }
  out.push({ piece: word.slice(start), start: offset + start });
  return out;
}

/** Tokenize text into canonical tokens with original offsets; stopwords dropped. */
function tokenize(text: string): Tok[] {
  const toks: Tok[] = [];
  for (const m of text.matchAll(/[\p{L}\p{N}]+/gu)) {
    for (const { piece, start } of camelPieces(m[0], m.index ?? 0)) {
      if (piece.length < 2) continue;
      const folded = fold(piece);
      if (STOPWORDS.has(folded)) continue;
      const stemmed = stem(folded);
      toks.push({
        canon: SYNONYM_MAP.get(stemmed) ?? stemmed,
        start,
        end: start + piece.length,
      });
    }
  }
  return toks;
}

/** Exact canonical match, with a >=4-char prefix fallback (tacti ~ tactile). */
function tokenMatches(a: string, b: string): boolean {
  if (a === b) return true;
  if (a.length >= 4 && b.length >= 4) return a.startsWith(b) || b.startsWith(a);
  return false;
}

// ---------------------------------------------------------------------------
// Per-venture document
// ---------------------------------------------------------------------------

const FIELD_WEIGHTS = {
  name: 3,
  tags: 2.5,
  one_liner: 2,
  rationale: 1,
  evidence: 0.75,
} as const;

/** A single query token maxes out here even if it appears in every field. */
const PER_TOKEN_CAP = 4.5;
const BIGRAM_BONUS = 1.25;
const MAX_SNIPPET_BODY = 88; // + up to 2 ellipsis chars = 90 total

interface DocField {
  field: string;
  weight: number;
  text: string;
  toks: Tok[];
}

const docCache = new WeakMap<RankedVenture, DocField[]>();

function docOf(v: RankedVenture): DocField[] {
  const cached = docCache.get(v);
  if (cached) return cached;

  const fields: DocField[] = [];
  const push = (field: string, weight: number, text: string | null | undefined) => {
    if (!text || !text.trim()) return;
    fields.push({ field, weight, text, toks: tokenize(text) });
  };

  push("name", FIELD_WEIGHTS.name, v.name);
  push("tags", FIELD_WEIGHTS.tags, (v.market_tags ?? []).join(" · "));
  push("one_liner", FIELD_WEIGHTS.one_liner, v.one_liner);

  const categories = v.breakdown?.categories ?? {};
  for (const [key, cat] of Object.entries(categories)) {
    if (!cat) continue;
    push(`rationale:${key}`, FIELD_WEIGHTS.rationale, cat.rationale ?? null);
    const evidenceText = (cat.evidence ?? [])
      .flatMap((e) => [e.claim, e.snippet ?? ""])
      .filter(Boolean)
      .join(" · ");
    push(`evidence:${key}`, FIELD_WEIGHTS.evidence, evidenceText);
  }

  docCache.set(v, fields);
  return fields;
}

// ---------------------------------------------------------------------------
// locationOf — city derivation (explicit mention or institution inference)
// ---------------------------------------------------------------------------

const CITY_PATTERNS: [RegExp, string][] = [
  [/\bZ[üu]rich\b/iu, "Zurich"],
  [/\bLausanne\b/i, "Lausanne"],
  [/\bGen(?:eva|ève|eve)\b/iu, "Geneva"],
  [/\bBerne?\b/i, "Bern"],
  [/\bSion\b/i, "Sion"],
  [/\bBasel\b/i, "Basel"],
  [/\bZug\b/i, "Zug"],
  [/\bM[üu]nchen\b/iu, "Munich"],
  [/\bMunich\b/i, "Munich"],
  [/\bStockholm\b/i, "Stockholm"],
  [/\bCopenhagen\b/i, "Copenhagen"],
  [/\bK[øo]benhavn\b/iu, "Copenhagen"],
];

/** Case-sensitive on purpose: "ETH" must not match "ethernet"/"method". */
const INSTITUTION_PATTERNS: [RegExp, string][] = [
  [/\bETHZ?\b/, "Zurich"],
  [/\bUZH\b/, "Zurich"],
  [/\bEPFL\b/, "Lausanne"],
  [/\bUNIGE\b/, "Geneva"],
  [/\bCERN\b/, "Geneva"],
  [/\bKTH\b/, "Stockholm"],
  [/\bDTU\b/, "Copenhagen"],
  [/\bTUM\b/, "Munich"],
  [/\bTU M[üu]nchen\b/u, "Munich"],
  [/\bTU Munich\b/, "Munich"],
];

function canonicalCity(raw: string): string {
  for (const [re, city] of CITY_PATTERNS) if (re.test(raw)) return city;
  return raw;
}

function countMatches(text: string, re: RegExp): number {
  const global = new RegExp(re.source, re.flags.includes("g") ? re.flags : re.flags + "g");
  let n = 0;
  while (global.exec(text) !== null) n++;
  return n;
}

/**
 * Derive a city for a venture. Prefers a future `location` field on the row
 * (string or {city, confidence?}) when present; otherwise scans one_liner,
 * rationales and evidence claims/snippets for city + institution mentions.
 */
export function locationOf(v: RankedVenture): LocationGuess | null {
  // Future-proofing: prefer an explicit location column when the contract grows one.
  const forward = (v as { location?: unknown }).location;
  if (typeof forward === "string" && forward.trim()) {
    return { city: canonicalCity(forward.trim()), confidence: "explicit" };
  }
  if (forward && typeof forward === "object") {
    const rec = forward as { city?: unknown; confidence?: unknown };
    if (typeof rec.city === "string" && rec.city.trim()) {
      const confidence = rec.confidence === "inferred" ? "inferred" : "explicit";
      return { city: canonicalCity(rec.city.trim()), confidence };
    }
  }

  const text = docOf(v)
    .map((f) => f.text)
    .join(" · ");
  if (!text) return null;

  // score = explicit mentions x2 + institution mentions; explicit wins ties via weight.
  const scores = new Map<string, { score: number; explicit: boolean; order: number }>();
  const bump = (city: string, weight: number, explicit: boolean) => {
    const cur = scores.get(city) ?? { score: 0, explicit: false, order: scores.size };
    cur.score += weight;
    cur.explicit = cur.explicit || explicit;
    scores.set(city, cur);
  };
  for (const [re, city] of CITY_PATTERNS) {
    const n = countMatches(text, re);
    if (n > 0) bump(city, n * 2, true);
  }
  for (const [re, city] of INSTITUTION_PATTERNS) {
    const n = countMatches(text, re);
    if (n > 0) bump(city, n, false);
  }
  if (scores.size === 0) return null;

  let best: { city: string; score: number; explicit: boolean; order: number } | null = null;
  for (const [city, s] of scores) {
    if (!best || s.score > best.score || (s.score === best.score && s.order < best.order)) {
      best = { city, ...s };
    }
  }
  return best ? { city: best.city, confidence: best.explicit ? "explicit" : "inferred" } : null;
}

// ---------------------------------------------------------------------------
// Option derivation (for the QueryBar chip rows)
// ---------------------------------------------------------------------------

/** Union of market_tags across the pool, deduped case-insensitively, sorted. */
export function sectorOptionsOf(ventures: RankedVenture[]): string[] {
  const seen = new Map<string, string>();
  for (const v of ventures) {
    for (const tag of v.market_tags ?? []) {
      const key = fold(tag);
      if (key && !seen.has(key)) seen.set(key, tag);
    }
  }
  return [...seen.values()].sort((a, b) => a.localeCompare(b));
}

/** Distinct cities derivable from the pool via locationOf, sorted. */
export function locationOptionsOf(ventures: RankedVenture[]): string[] {
  const cities = new Set<string>();
  for (const v of ventures) {
    const loc = locationOf(v);
    if (loc) cities.add(loc.city);
  }
  return [...cities].sort((a, b) => a.localeCompare(b));
}

// ---------------------------------------------------------------------------
// Structured filters
// ---------------------------------------------------------------------------

function passesFilters(v: RankedVenture, q: VentureQuery, city: string | null): boolean {
  if (q.sectors.length > 0) {
    const tags = new Set((v.market_tags ?? []).map(fold));
    if (!q.sectors.some((s) => tags.has(fold(s)))) return false;
  }
  if (q.locations.length > 0) {
    if (!city) return false;
    const target = fold(city);
    if (!q.locations.some((l) => fold(l) === target)) return false;
  }
  if (q.minScore != null && v.final_score < q.minScore) return false;
  if (q.statuses.length > 0 && !q.statuses.includes(v.status)) return false;
  if (q.tiers.length > 0) {
    const tier: TierFilter = v.quality_tier == null ? "untiered" : v.quality_tier;
    if (!q.tiers.includes(tier)) return false;
  }
  return true;
}

// ---------------------------------------------------------------------------
// Text scoring
// ---------------------------------------------------------------------------

interface FieldMatch {
  field: DocField;
  /** Doc tokens that matched some query token (for snippets). */
  toks: Tok[];
  /** Distinct query concepts found in this field. */
  distinct: number;
}

function scoreVenture(
  v: RankedVenture,
  uniq: string[],
  pairs: [string, string][],
): { relevance: number; matched: MatchedSnippet[] } {
  const doc = docOf(v);
  const perField = new Map<DocField, Set<Tok>>();
  const perFieldDistinct = new Map<DocField, Set<string>>();

  let raw = 0;
  for (const qt of uniq) {
    let tokenScore = 0;
    for (const f of doc) {
      let hit = false;
      for (const dt of f.toks) {
        if (tokenMatches(qt, dt.canon)) {
          hit = true;
          let set = perField.get(f);
          if (!set) perField.set(f, (set = new Set()));
          set.add(dt);
        }
      }
      if (hit) {
        tokenScore += f.weight;
        let d = perFieldDistinct.get(f);
        if (!d) perFieldDistinct.set(f, (d = new Set()));
        d.add(qt);
      }
    }
    raw += Math.min(tokenScore, PER_TOKEN_CAP);
  }

  for (const [a, b] of pairs) {
    const found = doc.some((f) => {
      for (let i = 0; i + 1 < f.toks.length; i++) {
        if (tokenMatches(a, f.toks[i].canon) && tokenMatches(b, f.toks[i + 1].canon)) return true;
      }
      return false;
    });
    if (found) raw += BIGRAM_BONUS;
  }

  const max = uniq.length * PER_TOKEN_CAP + pairs.length * BIGRAM_BONUS;
  const relevance = max > 0 ? Math.round(Math.min(1, raw / max) * 10000) / 10000 : 0;
  if (relevance <= 0) return { relevance: 0, matched: [] };

  const candidates: FieldMatch[] = [...perField.entries()].map(([field, toks]) => ({
    field,
    toks: [...toks].sort((a, b) => a.start - b.start),
    distinct: perFieldDistinct.get(field)?.size ?? 0,
  }));
  candidates.sort((a, b) => b.distinct - a.distinct || b.field.weight - a.field.weight);

  const matched: MatchedSnippet[] = [];
  const seen = new Set<string>();
  for (const c of candidates) {
    if (matched.length >= 3) break;
    const snip = buildSnippet(c.field, c.toks);
    if (seen.has(snip.snippet)) continue;
    seen.add(snip.snippet);
    matched.push(snip);
  }
  return { relevance, matched };
}

/** Extract a <=90-char fragment around the densest cluster of matched tokens. */
function buildSnippet(field: DocField, toks: Tok[]): MatchedSnippet {
  const text = field.text;

  // Anchor: matched token with the most matched neighbours within the window.
  let anchor = toks[0];
  let bestDensity = -1;
  for (const t of toks) {
    const density = toks.filter((o) => o.start >= t.start && o.start < t.start + 70).length;
    if (density > bestDensity) {
      bestDensity = density;
      anchor = t;
    }
  }

  let winStart = Math.max(0, anchor.start - 30);
  if (winStart > 0) {
    const sp = text.lastIndexOf(" ", winStart);
    if (sp >= 0 && winStart - sp <= 12) winStart = sp + 1;
  }
  let winEnd = Math.min(text.length, winStart + MAX_SNIPPET_BODY);
  if (winEnd < text.length) {
    const sp = text.lastIndexOf(" ", winEnd);
    if (sp > winStart + 40) winEnd = sp;
  }
  while (winStart < winEnd && text[winStart] === " ") winStart++;
  while (winEnd > winStart && text[winEnd - 1] === " ") winEnd--;

  const prefix = winStart > 0 ? "…" : "";
  const suffix = winEnd < text.length ? "…" : "";
  const body = text.slice(winStart, winEnd);
  const ranges: [number, number][] = [];
  for (const t of toks) {
    if (t.start >= winStart && t.end <= winEnd) {
      ranges.push([t.start - winStart + prefix.length, t.end - winStart + prefix.length]);
    }
  }
  return { field: field.field, snippet: prefix + body + suffix, ranges };
}

// ---------------------------------------------------------------------------
// runQuery
// ---------------------------------------------------------------------------

/**
 * Apply structured filters, then (if the query has text) score and re-rank.
 * With text: only relevance > 0 hits are returned, sorted by relevance desc
 * (tie: final_score desc) — the UI shows "n of m match".
 * Without text: relevance is null and the input (ranking) order is preserved.
 */
export function runQuery(ventures: RankedVenture[], q: VentureQuery): QueryHit[] {
  const withCity = ventures.map((v) => ({ v, city: locationOf(v)?.city ?? null }));
  const filtered = withCity.filter(({ v, city }) => passesFilters(v, q, city));

  const queryToks = tokenize(q.text);
  if (queryToks.length === 0) {
    return filtered.map(({ v, city }) => ({ venture: v, relevance: null, matched: [], city }));
  }

  const uniq = [...new Set(queryToks.map((t) => t.canon))];
  const pairs: [string, string][] = [];
  for (let i = 0; i + 1 < queryToks.length; i++) {
    pairs.push([queryToks[i].canon, queryToks[i + 1].canon]);
  }

  const hits: QueryHit[] = [];
  for (const { v, city } of filtered) {
    const { relevance, matched } = scoreVenture(v, uniq, pairs);
    if (relevance > 0) hits.push({ venture: v, relevance, matched, city });
  }
  hits.sort(
    (a, b) =>
      (b.relevance ?? 0) - (a.relevance ?? 0) || b.venture.final_score - a.venture.final_score,
  );
  return hits;
}
