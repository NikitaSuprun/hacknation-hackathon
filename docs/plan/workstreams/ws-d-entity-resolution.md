# WS-D — Entity resolution

**Owner**: 1 dev · **Timing**: ~3 days · **Depends on**: WS0 fixtures (builds Day 1); quality-gates real data for WS-E.
**Goal**: link GitHub users, paper authors, and Zefix officers into golden `silver.person` records with confidence + provenance; keep merges reversible; measure precision.

**Reference**: [entity-resolution.md](../reference/entity-resolution.md) · [data-model § silver](../reference/data-model.md)

## Checklist

- [ ] **T6 — Stage-0 normalizer** (bronze → PSR, per-source extractors; reuse `tools/norm.py`)
  - [ ] *Acceptance*: fixture bronze rows produce byte-exact expected PSR rows (golden-file test); idempotent
- [ ] **T7 — Deterministic pass (D1–D6)** with cross-link priors (Stage 1)
  - [ ] *Acceptance*: Fischer's 3 PSRs → 1 person; the two Wei Zhangs stay separate; every link has method+evidence; re-run adds 0 links
- [ ] **T8 — Splink pass** (DuckDB local; blocking + comparisons per the reference)
  - [ ] *Acceptance*: end-to-end <5 min on full dev data; ≥0.90 auto-links written; 0.60–0.90 pairs land in adjudication input; comparison vectors stored in `evidence`
- [ ] **T9 — LLM adjudication + review queue** (`ai_query` Sonnet 4.6 primary; Anthropic Batches Opus 4.8 fallback)
  - [ ] *Acceptance*: 100% of band pairs get schema-valid JSON verdicts; `match`→link@0.90; `unsure`→`ops.er_review_queue`; `no_match` persisted so re-runs skip
- [ ] **T10 — Survivorship + person builder + denorm refresh + `person_connection`**
  - [ ] *Acceptance*: canonical fields per precedence; `contribution.person_id` backfilled; all 3 edge types present; `chk_conn_order` holds; conflicting sources flagged
- [ ] **T11 — Embeddings job + similarity view** (`databricks-gte-large-en`, L2-normalize, `v_person_similarity`)
  - [ ] *Acceptance*: every person with ≥1 fact has a unit-norm 1024-dim vector; Fischer tops domain-fit vs the robotics ideal fixture
- [ ] **T12 — Erasure script + suppression wiring** (`tools/erase_person.py`)
  - [ ] *Acceptance*: erasing a fixture person removes/tombstones across all four schemas, writes `erasure_log`; a normalizer re-run does not resurrect them
- [ ] **T13 — Incremental orchestration** (`scrape_state` watermark; nightly full-ER script)
  - [ ] *Acceptance*: injecting 1 new bronze row flows to person + connections + score-input via one command; cursors advance; re-run idempotent
- [ ] **T-QA — Quality** : golden-set ER precision (target ≥95%, false-merge rate tracked) + corroboration/`is_provisional` flags + `ops.data_quality_report`
  - [ ] *Acceptance*: precision report generated each cycle; single-source facts stay provisional

## Risks
- False merges poison scores/memos/outreach → 0.90 floor, no name-only merges, same-source-collision review, reversible links, unmerge script.
- Deterministic-match yield may be <60–70% (noreply/private emails, missing ORCIDs) → the cross-link stage + Splink band + interview backfill absorb the residue.
