# WS0 — Platform & contracts

**Owner**: 1 dev + 1 floater · **Timing**: Day 0–1 · **Blocks**: everyone — do first.
**Goal**: stand up the workspace, freeze the data contract + interfaces, and load fixtures so all other workstreams build against `dealflow_dev` without waiting for live scrapers.

**Reference**: [data-model](../reference/data-model.md) · [interfaces](../reference/interfaces.md) · [engineering-standards](../reference/engineering-standards.md) · [compliance](../reference/compliance.md)

## Checklist

- [ ] **T0 — Workspace + gate bootstrap**
  - [ ] Databricks **Free Edition** workspace; catalogs `dealflow` + `dealflow_dev`; serverless SQL warehouse; service principal (M2M OAuth) for `databricks-sql-connector`
  - [ ] **Model smoke test**: `ai_query('databricks-gte-large-en','hi')` returns 1024 floats; document which `databricks-claude-*` endpoints resolve; record the Anthropic-API fallback decision
  - [ ] Repo scaffold: `uv` + `pyproject.toml` + `poe`; full pre-commit gate (ruff, basedpyright+ty, pydoclint, custom hooks, `pip-licenses`→`THIRD_PARTY_LICENSES`) + `.github/workflows/ci.yml`
  - [ ] *Acceptance*: `SELECT 1` via connector; `uv run pre-commit run --all-files` green on the skeleton
- [ ] **T1 — Apply DDLs** (`schemas/ddl/00_catalog.sql … 50_views.sql`, `tools/apply_ddl.py`)
  - [ ] *Acceptance*: all tables/views exist in both catalogs; CHECK constraints active; re-run is a no-op
- [ ] **T2 — `tools/ids.py` + `tools/norm.py`** with unit tests (noreply emails, ETH aliases, diacritics)
  - [ ] *Acceptance*: pytest green; identical input → identical UUID on two machines
- [ ] **T3 — `tools/db.py` `merge_upsert`** (Parquet→Volume→MERGE; `content_hash` skip; erasure-suppression guard)
  - [ ] *Acceptance*: double-run reports 0 inserted/0 updated; changed-hash row updates; a seeded suppressed key is blocked
- [ ] **T3b — Interface layer**: `BaseScraper`/`Sink`/`SourceNormalizer`/`LLMClient`/`EnrichmentProvider`/`FundedFounderResolver`/`CategoryScorer`/`InstitutionScorer` ABCs + JSON Schemas (evidence/breakdown/memo/ideal/interview) + `tests/contracts/` CI gate
  - [ ] *Acceptance*: contract tests run in CI; a schema-violating fixture fails them
- [ ] **T4 — Fixtures** + `fixtures/validate.py`
  - [ ] Persona 1 "Lena Fischer" golden path across all 3 sources → 1 person → venture → score → memo → interview
  - [ ] Personas 2/3 two unmergeable "Wei Zhang"s (0.6–0.9 band → adjudication + review queue)
  - [ ] Persona 4 commit-email match (D2); Persona 5 ORCID-only (D1); Persona 6 retracted-link (unmerge shape)
  - [ ] Planted noise repos (awesome-list / course / bot) for the venture-likeness gate; fake seeded embeddings (`fake_embedding.py`, unit-norm 1024-dim)
  - [ ] *Acceptance*: validator passes — FK integrity, enum/CHECK validity, exactly one active link per PSR, one `is_latest` score per venture
- [ ] **T5 — Load fixtures to `dealflow_dev` + contract FREEZE** + `docs/contract.md` (join paths, view columns/types, status machines, example proxy queries)
  - [ ] *Acceptance*: `gold.v_ranked_ventures`/`v_venture_team`/`v_person_signals` return persona data; UI + scoring teams confirm unblocked; additive-only from here

## Risks
- Free Edition "certain models not available" / fair-use shutoff → T0 smoke test + Anthropic fallback + local Splink.
- Contract churn across 6 sessions → Day-1 freeze, fixtures as executable contract, UI reads views only, one contract owner.
