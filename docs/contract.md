# The data contract

**Status: prepared, not yet frozen.** The freeze happens after the warehouse
steps in [runbooks/databricks.md](runbooks/databricks.md) pass and every
workstream lead signs off. From that moment every change here is
**additive-only**: add nullable columns or new tables; never remove, rename,
or retype anything below.

Full DDLs live in `schemas/ddl/` (source of truth); design rationale in
[docs/plan/reference/data-model.md](plan/reference/data-model.md). Fixtures in
`fixtures/data/` are the executable form of this contract - if your code works
against `dealflow_dev`, it works.

## Catalogs

`dealflow` (live scraped data) and `dealflow_dev` (identical structure, loaded
from fixtures - build against this one) each hold `bronze`, `silver`, `gold`,
`ops` plus the `ops.staging` volume the shared sink writes through.

## Views (the only surface the UI/proxy reads)

| View | Columns |
|---|---|
| `gold.v_ranked_ventures` | venture_id, name, one_liner, status, quality_tier, market_tags, final_score, confidence, ideal_match, s_individual_experience, s_schools, s_network_ties, s_prior_collaboration, s_problem_realness, s_product_defensibility, s_market, s_traction, breakdown, scored_at |
| `gold.v_venture_team` | venture_id, person_id, full_name, headline, github_login, orcid, linkedin_url, affiliation, avatar_url, role_hint, is_founder_guess, weight, evidence |
| `gold.v_person_network` | person_id, people_connected (sorted array of struct(weight, other_person_id, connection_type)) |
| `gold.v_person_similarity` | person_id, profile_id, domain_fit |
| `gold.v_person_signals` | person_id, signal_type ('contribution'\|'authorship'\|'officer'), artifact_id, artifact_name, role, magnitude (INT: commits or citations, NULL for officers), confidence, source_url, occurred_at |

The Statement Execution API returns VARIANT columns (`breakdown`, `evidence`,
`sections`) as JSON **strings** - the proxy/UI parses them client-side.

## Canonical join paths

```sql
-- 1) All signals for person X -> gold.v_person_signals WHERE person_id = :x
--    person -> person_source_link(active) -> person_source_record
--           -> {contribution|authorship|officer} -> artifact
-- 2) The team behind venture Y -> gold.v_venture_team WHERE venture_id = :y
--    venture -> venture_member -> person
-- 3) Who collaborated with whom -> silver.person_connection
--    (undirected edges; person_a_id < person_b_id)
```

## Status machines (DDL CHECK constraints are authoritative)

- `silver.person.status`: `active | merged | erased`
- `silver.person_source_link.status`: `active | retracted` - at most one
  active link per source_record_id (ER-job invariant; the fixture validator
  enforces exactly one)
- `gold.venture.status`: `sourced | scored | shortlisted | outreach |
  interviewing | passed | archived`
- `gold.outreach.status`: `draft | approved | sent | bounced | replied |
  consented | declined | interview_scheduled | interview_started |
  interviewed | closed | opted_out | expired`
  (the frontend reference's shorter list is UI shorthand; this list wins)
- `gold.venture_score`: append-only; exactly one `is_latest` row per venture
- `gold.memo`: append-only versions; serve `is_latest`

## Deterministic IDs (frozen input strings)

`DEALFLOW_NS = uuid5(NAMESPACE_URL, 'dealflow.hacknation.2026')`; ids are
`str(uuid5(DEALFLOW_NS, input))` minted **only** via `tools/ids.py`:

| Entity | Input string |
|---|---|
| person_source_record | `{source}:{source_key}` (zefix source_key is `{uid}:{name_norm}`; arxiv author is `{arxiv_id}:{position}`) |
| project | `github_repo:{repo_id}` |
| publication | `{doi}` else `arxiv:{arxiv_id}` else `{openalex_id}` |
| company | `zefix:{uid}` |
| venture | `{anchor_type}:{anchor_id}` |
| contribution | `{project_id}{source_record_id}` |
| authorship | `{publication_id}{source_record_id}` |
| officer | `{company_id}{source_record_id}{role_norm}` |
| person_source_link | `{person_id}{source_record_id}{match_method}` |
| institution_score | ROR id when known, else canonical name |

`person` and event rows (scores, memos, outreach, interviews) are random
UUIDv4 - never derived, never reused.

## Python interfaces (import paths)

- `contracts.interfaces`: `BaseScraper`, `Sink`, `SourceNormalizer`,
  `LLMClient`, `EnrichmentProvider`, `FundedFounderResolver`,
  `InstitutionScorer`, `CategoryScorer` (all Protocols).
  Note: `Sink.upsert` takes `variant_cols: frozenset[str]` (immutable
  tightening of the reference's `set[str]`) and `rows: list[SinkRow]`.
- `contracts.models`: the frozen value types (`PersonSourceRecord`,
  `UpsertResult`, `CategoryScore`, `Evidence`, ...) plus the type aliases
  every producer uses: `Json` (parsed JSON) and `SinkValue`/`SinkRow`
  (JSON shape plus typed datetime/date cells, any nesting depth).
- `tools.db.DatabricksSink`: the shared Sink implementation
  (canonical JSON -> Parquet -> `ops.staging` volume -> one MERGE, content-hash
  skip, erasure-suppression guard). Every target must be a table in
  `schemas/ddl` - staging Arrow schemas, VARIANT detection, and complex-column
  comparison all come from `tools.ddl_registry`, and identifiers are validated
  at entry. `tools.ids` is the only id mint.
- Normalizers: `tools.norm` (mechanical - `name_norm`, `email_norm`,
  `email_domain`, `org_key`, `url_norm`) and `tools.institutions`
  (`resolve`, `org_norm`) for semantic organisation folding backed by the CC0
  ROR seed in `data/institutions/`. PSR `org_norm` is the mechanically-normed
  ROR display name when resolved (`"KTH"` -> `"kth royal institute of
  technology"`), else the mechanical key.

## Payload JSON Schemas (`contracts/schemas/`, CI-enforced)

| Schema | Validates | Producer -> consumer |
|---|---|---|
| `evidence` | the uniform evidence element | scorers/memo -> UI |
| `breakdown` | `gold.venture_score.breakdown` | WS-E -> UI |
| `memo` | `gold.memo.sections` (9 fixed sections; every bullet cited or `missing`) | WS-E -> UI |
| `ideal` | `gold.ideal_candidate.profile_json` | UI -> WS-E |
| `interview` | `gold.interview.extracted` | WS-F -> WS-D/WS-E |

`tests/contracts/` fails CI when a payload drifts; extend schemas
additive-only (new optional properties; `schema_version` bumps for anything
else).

## Example proxy queries (Statement Execution API, named parameters)

```sql
-- /v1/ranking?thesis_id=
SELECT r.* FROM gold.v_ranked_ventures r
JOIN gold.candidate_pool cp ON cp.venture_id = r.venture_id
WHERE cp.thesis_id = :thesis_id AND cp.included ORDER BY r.final_score DESC;

-- /v1/venture/:id/memo
SELECT sections, model_version, generated_at FROM gold.memo
WHERE venture_id = :venture_id AND is_latest;

-- /v1/venture/:id/team
SELECT * FROM gold.v_venture_team WHERE venture_id = :venture_id;

-- weights save (client re-ranks locally; no job)
MERGE INTO gold.score_weights t USING (SELECT :weights_id AS weights_id) s
ON t.weights_id = s.weights_id
WHEN MATCHED THEN UPDATE SET w_market = :w_market, updated_at = current_timestamp();
```

## Reserved additions (planned, additive - do not block on them)

- `ops.llm_adjudications` (WS-D stage 4), `gold.score_run` (WS-E triggers)
- `sources/hacknation/` + `HacknationNormalizer` + ER rules D7/D8 (WS-G)
- `scrapers/common/` shared runner library (WS-A/B/C half-day task)
- Model smoke-test outcome: after `poe smoke`, record here which
  `databricks-claude-*` endpoints resolve and whether the Anthropic-API
  fallback is active.
