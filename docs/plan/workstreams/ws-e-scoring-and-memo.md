# WS-E — Scoring & memo

**Owner**: 1 dev · **Timing**: ~3.5 days · **Depends on**: WS0 fixtures (builds Day 1); real quality gated by WS-D.
**Goal**: turn resolved signals into ventures-with-teams, score them (8 rubric categories + structured ideal-match over a shared feature layer + confidence), and generate cited investment memos; rescore on triggers.

**Reference**: [scoring-and-memo.md](../reference/scoring-and-memo.md) · [interfaces § CategoryScorer/EnrichmentProvider/FundedFounderResolver](../reference/interfaces.md) · [data-model § gold](../reference/data-model.md)

## Checklist

- [ ] **A1b — `institution_score` + funding backbone**
  - [x] University table (Leiden CC0 prestige + PitchBook/Dealroom outcome + European floor; ROR aliases; seed tiers) *(scoring/institution_seed.py byte-reproduces the golden file; 50/50 blend unit-tested)*
  - [x] Company table (curated tiers + Accel/SignalFire founder-factory upgrades; aliases) *(fixture-scale seed; the factory-upgrade list is a follow-up when the full curated table lands)*
  - [x] `FundedFounderResolver` cascade (SOGC capital-increase / Startupticker / Crunchbase-2013 / Wikidata) → `{funded, stage, amount, date, source}` *(SOGC HR02 + static-list stages implemented in scoring/funding.py; Startupticker/Crunchbase/Wikidata sources plug into the same static-list stage later)*
  - [x] *Acceptance*: MIT>KTH gap present; a fixture funded founder resolves `funded=true` with a source *(Jonas Keller → `static_list`; tests/scoring/test_funding.py)*
- [ ] **A2 — Venture builder** (repo/company/paper grouping, merge rules, `is_corporate_oss`/`is_academic`/solo flags + **venture-likeness gate** rejecting awesome-lists/courses/dotfiles/demos)
  - [x] Repo + company anchors, merge rules, likeness/corporate gates *(byte-reproduces gold.venture + gold.venture_member)*
  - [ ] Paper-cluster + hackathon anchors *(not needed by the fixture personas; cut for the hackathon window)*
  - [x] *Acceptance*: fixtures produce expected ventures; corporate-OSS/noise cases unit-tested *(tests/scoring/test_ventures.py)*
- [x] **A3 — `person_features` + collab graph** (deterministic; NULL=unknown, never zero)
  - [x] *Acceptance*: features for all venture persons; graph centrality computed *(gold.person_features byte-reproduced under the calibration seam; real formulas unit-tested with documented divergences)*
- [ ] **A4 — LLM micro-tasks** (`ai_query` Haiku: commit quality on ~20 sampled commits, experience-fit)
  - [x] Extractors + TASK-tag scripts (`TASK:commit_quality`, `TASK:experience_fit`) wired through the LLMClient seam
  - [ ] *Acceptance*: 0–100 + rationale persisted; cost row in `ops.llm_run_log` *(offline path green; live ai_query persistence needs Databricks creds)*
- [x] **A5 — Embedding template + domain-fit** (deterministic renderer for persons + ideal; cosine)
  - [x] *Acceptance*: editing the ideal fixture measurably reorders domain-fit *(Lena tops the robotics ideal; a simulation/RL ideal reorders to Wei — tests/scoring/test_profile_text.py)*
- [x] **A6 — Stage-A category scorers** (1.1.1/1.1.2/1.1.4/2.2 + ideal-match) + confidence + `venture_gaps`
  - [x] *Acceptance*: `venture_score` + evidence JSON for every venture; confidence responds to removed fields; quality gate sets `needs_more_data` *(latest fixture row byte-reproduced; breakdown hard-validated against the frozen schema)*
- [x] **A7 — Thesis→`candidate_pool`** (incl. no-VC heuristics + SOGC capital-increase check)
  - [x] *Acceptance*: changing the thesis fixture changes the pool; `exclusion_reasons` populated *(tests/scoring/test_pool.py)*
- [ ] **A8 — Stage-B deep-dive agent** (Anthropic + `web_search`, caps, caching) for 2.1/2.3/2.4 + funded-founder verification (1.1.3)
  - [x] Agent loop with 12-search cap, weekly (venture, category, ISO-week) cache, `ops.llm_run_log` spend rows; offline scripted-transport tests
  - [ ] *Acceptance*: top-K scored with URL-cited evidence; cost/venture <$1 logged *(offline proxies green incl. the refused 13th search; live run needs `ANTHROPIC_API_KEY`)*
- [x] **A9 — Memo job** (structured outputs, 9 sections, missing-markers)
  - [x] *Acceptance*: memo JSON schema-validates; zero uncited non-missing bullets *(gold.memo byte-reproduced; `assert_all_bullets_cited` raises typed errors as belt-and-braces)*
- [ ] **A10 — Orchestration** (Jobs wiring for triggers + interview extraction + targeted rescore)
  - [x] Interview ingestion + targeted Stage-A rerun + memo regen + `gold.score_run` idempotency ledger *(reproduces the two-row venture_score fixture history; duplicate ingest is a no-op)*
  - [ ] Databricks Jobs wiring for nightly/ideal-edit triggers *(needs workspace access; the CLI subcommands are the job entrypoints)*
  - [x] *Acceptance*: completing a fixture interview changes scores and regenerates the memo, idempotently *(tests/scoring/test_rescore.py)*

## Run notes

- CLI: `uv run python -m scoring <seed-institutions|ventures|features|stage-a|pool|stage-b|memo|rescore> [--fixtures] [--dry-run] [--catalog C] [--data-dir DIR] [--venture-id V] [--thesis-id T]`.
  `--fixtures --dry-run` is the zero-credential CI path: NullSink + ScriptedLLMClient over
  `scoring/scripted.py`, frozen fixture clock — it reproduces the committed gold files offline.
  Jobs read their inputs from `--data-dir` JSONL snapshots (fixtures/data by default); pointing the
  live path at a warehouse export is the follow-up once WS-D writes real silver.
- Live runs need Databricks creds (`.env.example`) for the sink + `ai_query`; Stage B additionally
  needs `ANTHROPIC_API_KEY` (`build_scoring_deps(..., stage_b=True)` fails fast without it).
- **Calibration-seam inventory** (verified fixture drift routed through explicit seams; the true
  formulas are unit-tested alongside):
  - `scoring.scripted.FIXTURE_CALIBRATION` — venture_score final 78.4 / confidence 0.82 (derived Σw·s = 78.9); `FIXTURE_CALIBRATION_OLD` — the pre-interview history row 74.1 / 0.7 (identical categories, different final).
  - `scoring.scripted.FIXTURE_OVERRIDES` — Wei `stars_weighted` 7.9 (derived 8.04); recency 0.95/0.9 (derived ~1.0 next-day decay); seeded profile texts (`LENA_TEXT`/`WEI_A_TEXT`).
  - Scripted category verdicts (`fixture_category_results`) carry the seeded `s_schools` 92 where the deterministic rule computes 97 on fixture data.
  - `scoring.scripted.FIXTURE_FEATURE_PROFILE` — the exact golden feature key set.
- `gold.score_run` (appended to `schemas/ddl/30_gold.sql`) is the rescore idempotency ledger:
  an ok run with the same `input_versions.fingerprint` (content hash of interview + snapshot)
  makes a repeat ingest a `skipped_duplicate` that writes no score/memo rows.

## Risks
- Deep-dive flakiness/cost on sparse Swiss footprints → hard caps (max_uses, token ceilings, K≤25), caching, run Stage B overnight; low-evidence is a valid outcome (lowers confidence, feeds interview).
- Silent truncation reads as "covered everything" → `log()` any dropped coverage; quality gate + confidence make thin data visible.
