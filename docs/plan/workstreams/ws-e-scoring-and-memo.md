# WS-E — Scoring & memo

**Owner**: 1 dev · **Timing**: ~3.5 days · **Depends on**: WS0 fixtures (builds Day 1); real quality gated by WS-D.
**Goal**: turn resolved signals into ventures-with-teams, score them (8 rubric categories + structured ideal-match over a shared feature layer + confidence), and generate cited investment memos; rescore on triggers.

**Reference**: [scoring-and-memo.md](../reference/scoring-and-memo.md) · [interfaces § CategoryScorer/EnrichmentProvider/FundedFounderResolver](../reference/interfaces.md) · [data-model § gold](../reference/data-model.md)

## Checklist

- [ ] **A1b — `institution_score` + funding backbone**
  - [ ] University table (Leiden CC0 prestige + PitchBook/Dealroom outcome + European floor; ROR aliases; seed tiers)
  - [ ] Company table (curated tiers + Accel/SignalFire founder-factory upgrades; aliases)
  - [ ] `FundedFounderResolver` cascade (SOGC capital-increase / Startupticker / Crunchbase-2013 / Wikidata) → `{funded, stage, amount, date, source}`
  - [ ] *Acceptance*: MIT>KTH gap present; a fixture funded founder resolves `funded=true` with a source
- [ ] **A2 — Venture builder** (repo/company/paper grouping, merge rules, `is_corporate_oss`/`is_academic`/solo flags + **venture-likeness gate** rejecting awesome-lists/courses/dotfiles/demos)
  - [ ] *Acceptance*: fixtures produce expected ventures; bot/corporate-OSS/solo/noise cases unit-tested
- [ ] **A3 — `person_features` + collab graph** (deterministic; NULL=unknown, never zero)
  - [ ] *Acceptance*: features for all venture persons; graph centrality computed
- [ ] **A4 — LLM micro-tasks** (`ai_query` Haiku: commit quality on ~20 sampled commits, experience-fit)
  - [ ] *Acceptance*: 0–100 + rationale persisted; cost row in `ops.llm_run_log`
- [ ] **A5 — Embedding template + domain-fit** (deterministic renderer for persons + ideal; cosine)
  - [ ] *Acceptance*: editing the ideal fixture measurably reorders domain-fit
- [ ] **A6 — Stage-A category scorers** (1.1.1/1.1.2/1.1.4/2.2 + ideal-match) + confidence + `venture_gaps`
  - [ ] *Acceptance*: `venture_score` + evidence JSON for every venture; confidence responds to removed fields; quality gate sets `needs_more_data`
- [ ] **A7 — Thesis→`candidate_pool`** (incl. no-VC heuristics + SOGC capital-increase check)
  - [ ] *Acceptance*: changing the thesis fixture changes the pool; `exclusion_reasons` populated
- [ ] **A8 — Stage-B deep-dive agent** (Anthropic + `web_search`, caps, caching) for 2.1/2.3/2.4 + funded-founder verification (1.1.3)
  - [ ] *Acceptance*: top-K scored with URL-cited evidence; cost/venture <$1 logged
- [ ] **A9 — Memo job** (structured outputs, 9 sections, missing-markers)
  - [ ] *Acceptance*: memo JSON schema-validates; zero uncited non-missing bullets
- [ ] **A10 — Orchestration** (Jobs wiring for triggers + interview extraction + targeted rescore)
  - [ ] *Acceptance*: completing a fixture interview changes scores and regenerates the memo, idempotently

## Risks
- Deep-dive flakiness/cost on sparse Swiss footprints → hard caps (max_uses, token ceilings, K≤25), caching, run Stage B overnight; low-evidence is a valid outcome (lowers confidence, feeds interview).
- Silent truncation reads as "covered everything" → `log()` any dropped coverage; quality gate + confidence make thin data visible.
