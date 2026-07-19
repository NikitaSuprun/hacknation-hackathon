# Scoring & memo

The heart of the product. Owned by [WS-E](../workstreams/ws-e-scoring-and-memo.md). Final model (confirmed): **8 evidence-cited rubric categories + a structured ideal-candidate match, over a shared calibrated feature layer, all VC-weighted.**

## Venture construction

Input: entity-resolved silver. Output: `gold.venture` + `gold.venture_member`.
- **Repo anchor → core contributors**: contribution share = commits by author in trailing 12mo / total; team = share ≥10%, or share ≥5% AND ≥10 commits; cap 8, ordered by share; `weight` = normalized share. Exclude bots.
- **Zefix company → officers**: all natural persons with signing authority; board-only `role='board'`, weight ×0.5.
- **Paper cluster → coauthor groups**: edges between authors with ≥2 joint papers in trailing 24mo; connected components of 2–6 whose papers are topically coherent (mean pairwise title+abstract cosine ≥ threshold); `weight` ∝ author-position credit (first/last boosted). Solo prolific author = single-person cluster only if they also have a repo/company signal.
- **Merge** (post-ER): two anchors merge when they share ≥2 golden persons, or 1 person + an explicit cross-reference (README names the company / paper links the repo / Zefix purpose matches repo name fuzzy ≥0.85). Deterministic `venture_id` = hash of the earliest-seen anchor.
- **Edge cases**: solo builder (1.1.4 N/A, weight renormalized); big-company OSS (`is_corporate_oss=true`, excluded by default); university lab account (`is_academic=true`, treat like a paper cluster).
- **Hack Nation project → `hackathon_project` anchor**: the given `team[]` (author = founder guess) → `venture_member` with `role_hint` from `role`; **auto-merges** with the GitHub-repo venture when `githubUrl` matches a scraped repo. The `structured` pitch (problem/solution/usp/impact/implementation/targetAudience) feeds the memo + 2.1 problem / 2.2 product directly; `university`→`institution_score`, `techStack`→keywords, `eventTitle`/`winner`/`jury_scope`→a hackathon signal.
- **Signal-vs-noise gate**: `venture_likeness` classifier rejects awesome-lists, courses/tutorials, dotfiles, book/demo/meme repos (stored as a flag, not deleted).

## Thesis → candidate pool

`build_candidate_pool` job reads a `gold.thesis` row → writes `gold.candidate_pool`. Filters: sector match (LLM-tagged venture sectors vs thesis taxonomy), geography, team size, corporate-OSS flag. **"Never raised VC"** is a tri-state `funding_signal`:
- `none_found` (include): incorporation <18mo or unincorporated anchor; no funding vocabulary in README/website (regex `seed|series [A-C]|raised|backed by|investors` + Haiku confirmation); not in a static funded list.
- `suspected` (include, flagged): weak hits (accelerator logo, ambiguous press).
- `confirmed_funded` (exclude when `require_no_prior_vc`): Stage-B web check, static funded lists, or **Swiss SOGC capital-increase filing** (see funding backbone).

Final verification is an explicit interview question; the memo marks the filter heuristic-until-interview.

## `gold.person_features` (deterministic first, LLM second)

| feature | definition | source |
|---|---|---|
| `stars_weighted` | Σ(stars × contribution share), log1p-scaled | GitHub |
| `commits_12mo`, `active_weeks_12mo` | volume + consistency | GitHub |
| `commit_quality_llm` | 0–100 from Haiku review of ~20 sampled commits (message + truncated diff ≤400 tok): tests, coherent scope, non-trivial logic; + 2-line rationale | GitHub + ai_query |
| `top_co_flag`, `top_co_names` | employment/affiliation match vs `institution_score` (company) | multi |
| `zero_to_one_flag` | prior founder signal: past Zefix officer, "founder" in profile, created a >500-star repo | multi |
| `citations_total`, `h_index_proxy`, `top_venue_count` | OpenAlex | papers |
| `research_code_link` | paper↔repo linkage strength | derived |
| `school_tier` | from `institution_score` (university); NULL if unknown | affiliations, interview |
| `graph_centrality` | degree + 2-hop reach on person↔person edges | derived |
| `recency_score` | exp-decay over days since last commit/paper/filing (half-life 90d) | multi |
| `experience_problem_fit` | 0–100 Haiku rubric: history text vs venture one-liner | ai_query |

Every feature row carries `sources` provenance; **NULL means unknown (feeds confidence), never zero.**

## Ideal-candidate match (ordinal-aware, NOT raw text cosine)

A plain profile embedding can't encode MIT>KTH or that 8,200 stars ≫ 82 — embeddings capture topic, not magnitude/prestige. So:
- **(a) Calibrated structured features** — education & employer resolved through `gold.institution_score` (MIT/KTH gap is an explicit tunable number), plus normalized citations / stars×share / commit-quality / centrality / recency / education-level / research→code.
- **(b) Narrow semantic domain-fit** — cosine between the candidate's *what-they-build/research* text and the ideal's (`databricks-gte-large-en`, 1024-dim, L2-normalized, SQL dot product; `gold.v_person_similarity`).

The ideal candidate is a point in this same feature space (the shape of the user's `numeric_features` JSON). **Match = VC-weighted per-feature closeness** (directional meets-or-exceeds), domain-fit as one component → interpretable ("education 78/100 KTH, domain-fit 0.91, citations p70, stars p95"). Venture-level = `0.6 × weighted-mean(member matches) + 0.4 × max(member match)`, min-max normalized within the thesis pool. The whole-profile embedding survives only as a minor tiebreaker.

## `gold.institution_score` — construction (verified sources, licensing-aware)

Our own hand-built table, seeded from license-clean sources; ship only openly-licensed data files, hand-curate the rest.

**Universities**: `score = 50·prestige + 50·outcome`.
- Prestige ← **Leiden Ranking Open Edition (CC0)** "Math & CS" PP(top-10%) percentile (the only prestige ranking legally shippable; QS/THE/ARWU/US News = no commercial license; CSRankings = CC BY-NC-ND, use only to hand-calibrate).
- Outcome ← PitchBook free founder-ranking articles + Dealroom European Spinouts + 2026 European Deep-Tech Report (ETH #1, EPFL #2 worldwide for deep-tech founders); log-scaled with a European floor (Dealroom EU spinout top-10 → outcome ≥0.75).
- Normalize via **ROR IDs (CC0)** alias table; unknown → 35, logged.
- **Seed**: 100 MIT/Stanford · 97 ETH Zurich · 95 Berkeley/Harvard/Cambridge/Oxford · 93 EPFL · 88 Imperial/TUM/Technion/CMU · 82 UCL/**KTH**/TU Delft/Edinburgh/Tel Aviv · 75 UZH/DTU/Aalto/LMU/HEC/INSEAD · 65 other Leiden-top-300 technical · 50 other accredited · 35 unknown.

**Companies**: curated prestige tier + founder-factory upgrade (+1 tier if in the free Accel×Dealroom "Founder Factories" or SignalFire "Unicorn DNA" lists).
- T1 95–100: Google/DeepMind/OpenAI/Anthropic/Meta/AWS/Apple/Microsoft/NVIDIA/Stripe/Palantir/McKinsey/BCG/Bain/DE Shaw/Jane Street/Citadel.
- T2 80–94: Netflix/Uber/Airbnb/Databricks/Snowflake/Goldman/Mistral/HuggingFace + EU factories Klarna/Spotify/Revolut/Adyen/Wise/Zalando.
- T3 60–79: N26/Monzo/Bolt/Celonis/UiPath + Swiss Proton/Nexthink/Scandit/Climeworks/IBM Research Zurich + ETH spin-offs ANYbotics/Verity/Lakera.
- T4 40–59: Big-4/Accenture/Siemens/ABB/UBS/Roche/Novartis. Unknown 30.
- Alias normalization (Alphabet/Google LLC/YouTube→GOOGLE; Facebook→META).

## Funding backbone (funded-founder + "exclude already-funded")

Free path: (1) **Zefix/SOGC capital-increase filings** = near-perfect free realtime proxy that a Swiss AG/GmbH raised a priced round — reuses the WS-C scraper; (2) **Startupticker SVCR** round list (CH ground truth); (3) **Crunchbase 2013 CC-BY snapshot** + **Wikidata SPARQL** (P112 founded-by, P69 educated-at, P2088 crosswalk) for global/historical baseline; optional **Crunchbase Pro ~$99/mo**.
"Funded founder?" cascade: person→company → Startupticker match → SOGC capital-increase (Zefix) → Crunchbase/Wikidata → emit `{funded, stage, amount, date, source}`. Self-reinforcing: founder-production stats from our own accumulating data become viable in ~2–3 quarters.

## The eight 0–100 category scores

Land in `gold.venture_score` (`s_*` columns) + `breakdown` VARIANT; uniform evidence element `{claim, source_type, source_url, snippet, weight}`.

| # | Category | Method | Formula / rubric | Evidence |
|---|---|---|---|---|
| 1.1.1 | Individual experience | SQL over person_features, aggregated `0.6×wmean + 0.4×max` | weights: top-co 25, GitHub volume+quality 30, 0→1 exp 20, awards/papers 15, exp-problem fit 10; subfeatures percentile-normalized | per-person subscores + top URLs |
| 1.1.2 | Schools | deterministic lookup | `0.7×max(school_tier) + 0.3×mean(known tiers)`; unknowns excluded + logged | affiliation strings + matched list |
| 1.1.3 | Connections to funded founders | graph + web verify (top-K) | paths on collab graph to `is_funded_founder`; direct=90, 2-hop=60, none=25 (low-confidence + interview question) | path description + URLs |
| 1.1.4 | Worked together before | SQL over overlap | ≥2 contexts or ≥2yrs=90; 1=65; current only=30; solo=N/A | shared artifacts + dates |
| 2.1 | Problem realness | **web-search agent** (Reddit/HN) | 90+ many independent complaints + paid workarounds; 70 recurring; 50 thin; ≤20 none | verbatim quotes + permalinks |
| 2.2 | Product & defensibility | batch ai_query (no web) | README + deps + star-velocity percentile + contributor growth + license; own-model/hard-tech high, thin wrapper low | README/dep lines + repo URL |
| 2.3 | Market | **web-search agent** | TAM/SAM/SOM with explicit assumptions, growth %, named competitors + funding; size×growth banded, discounted by competitor density | market URLs + assumption list |
| 2.4 | Traction | hybrid + interview | stars/forks/downloads + website/waitlist + PH/testimonials/jobs; users/LOIs/revenue interview-only (capped 70 until confirmed) | metric snapshots + `missing` markers |

**Category renormalization**: an N/A or zero-evidence category redistributes its weight pro-rata over the rest — never a silent 50.

## Final score & funnel

`final = Σ_{i∈8} w_i·cat_i + w_ideal_match·ideal_match`, all 9 weights VC-editable, renormalized. **Weights edit → no job** (raw category scores stored; final computed at read/client → instant re-rank).

- **Stage A (all candidates, ~$30–40 full refresh)**: deterministic features + ai_query micro-tasks (Haiku commit-quality/experience-fit) + embeddings + categories 1.1.1/1.1.2/1.1.4/2.2 + ideal-match.
- **Stage B (top-K≈25/thesis, ~$0.6–1.0/venture)**: Anthropic `claude-opus-4-8` + `web_search` (max 12 searches, token ceilings, results cached by venture/category/week) for 2.1/2.3/2.4 + funded-founder verification for 1.1.3.

## Confidence & gaps

`confidence = 100 × Σ_i w_i × coverage_i × diversity_i` (coverage = filled/required required-fields; diversity 1.0 if ≥2 source types, 0.8 one, 0.5 inference-only). Weighted by the VC's own weights → confidence drops where the VC cares. Unfilled fields ranked by `w_i × field_importance` → `gold.venture_gaps` → top ~8 become the interview question plan + fixed consent asks (LinkedIn URL, CV, funding history, traction metrics). **Quality gate**: below a minimum confidence threshold a venture is `quality_tier='needs_more_data'` (visible, clearly marked, feeds the interview) rather than scored as complete.

## Rescoring triggers (idempotent, append-only, `is_latest` served)

`gold.score_run(run_id, trigger, input_versions, status)`; scores are pure functions of (data snapshot, ideal version, rubric version). Triggers: weights edit = no job (client re-rank); ideal edit = re-embed 1 doc + refresh (seconds); interview completed = targeted A+B rerun + memo regen; new scrape = nightly full Stage A.

## Memo generation

Anthropic `claude-opus-4-8` with **structured outputs** (JSON schema = the 9 fixed sections: company_snapshot, investment_hypotheses, swot, team_and_history, problem_and_product, technology_and_defensibility, market_tam_sam_som{tam,sam,som,assumptions[]}, competition, traction_and_kpis). Every section is `bullets:[{text, evidence:[{source_url, source_type}], missing, gap_field?}]` — the prompt forbids uncited claims: a bullet carries ≥1 `source_url` or is `missing:true` with the `gap_field` that feeds the interview. Storage `gold.memo` (append-only versions; view serves latest → demo shows memo before vs after interview). Regen triggers: any rescore of that venture, interview ingestion, or the UI "Regenerate" button.
