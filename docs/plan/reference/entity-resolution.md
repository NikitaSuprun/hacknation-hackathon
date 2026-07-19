# Entity resolution

Link GitHub users, paper authors, and Zefix officers into golden `silver.person` records with confidence and full provenance. Owned by [WS-D](../workstreams/ws-d-entity-resolution.md). Every stage is idempotent and stamps `pipeline_version` on each link.

## Tooling — "do we already have this person?"

Entity resolution / record linkage is a well-tooled problem; do not hand-roll the probabilistic core.

| Tool | What | Fit |
|---|---|---|
| **Splink 4.0.16** (MoJ, MIT) | Fellegi–Sunter probabilistic linkage, unsupervised EM, calibrated probabilities, DuckDB/Spark backends | **Recommended.** ~5k records in seconds on a laptop (DuckDB) |
| Zingg | Spark-native ML ER | needs labeled training pairs + Spark plumbing — heavier than needed |
| dedupe | active-learning linkage | interactive labeling per schema; weaker calibration |
| Senzing | commercial ER engine | overkill + licensing friction |
| LLM-only | "same person?" per pair | not a substitute (no calibration, non-deterministic); correct role = **adjudicator of the ambiguous band** |

There is **no** compliant "GitHub → LinkedIn magic resolver" — vendors that appear to do it are built on scraped LinkedIn data. Our compliant recall path: public-source signals + Splink + LLM adjudication + **consent-based interview intake** (creates an `interview` PSR + `interview_claim` link).

## Pipeline

**Stage 0 — Normalize** (`er/normalize.py`): bronze → `person_source_record`, one extractor per source.
- `github`: one PSR per user; `source_key = str(user_id)`; emails from profile + distinct commit-author emails observed in our repos. GitHub noreply `{id}+{login}@users.noreply.github.com` attributes *commits* to a github identity but is **banned from cross-source email matching**.
- `openalex_author`: one PSR per OpenAlex author id (inherit their disambiguation); carries ORCID + institution when present.
- `arxiv_author`: PSR per `(arxiv_id, position)` only for papers with no OpenAlex coverage (fallback spine).
- `zefix_officer`: PSR per `(uid, name_norm)` from company payload + SOGC text (no registry person-id — a known Swiss-registry limitation).
- `hacknation`: PSR per Hack Nation `user_id` (from the people list + each project's `authorProfile` + `team[]`); carries `linkedin_url`, `cv_url`, university→`org_norm`, `field_of_study`/`techStack`→`keywords`, country/city. Feeds D7 (LinkedIn) and D8 (project `githubUrl`).
- Normalizers in `tools/norm.py`, unit-tested: `name_norm` (lower, strip diacritics/titles), `email_norm` (+ generic-inbox blacklist info@/admin@…), `org_norm` (strip AG/GmbH/SA/Sàrl; alias table folds ETHZ/ETH Zürich/Swiss Federal Institute of Technology → `eth zurich`, same EPFL/UZH), `url_norm`.

**Stage 1 — Artifact cross-links** (high-precision priors, before person matching): regex arXiv ids out of READMEs → `project.arxiv_ids_in_readme`; GitHub URLs out of OpenAlex/S2 metadata → `publication.code_urls`; also the PwC-archive `bronze.paper_code_links`. Each repo↔paper pair generates candidate person pairs (top contributors × authors).

**Stage 2 — Deterministic rules** (pure SQL over PSR; auto-link at ≥0.90):

| # | Rule | Confidence | Auto? |
|---|---|---|---|
| D1 | ORCID equality | 0.99 | yes |
| D2 | Non-generic email exact match | 0.98 | yes |
| D3 | Website/blog URL equality (normalized) | 0.95 | yes |
| D4 | Twitter/handle equality, or GitHub URL listed on the author's OpenAlex/homepage record | 0.95 | yes |
| D5 | Cross-linked artifact (Stage 1) + name match (Jaro-Winkler ≥ 0.92 on name_norm, or login ≈ concatenated name) | 0.92 | yes |
| D6 | Exact `name_norm` + same `org_norm` | 0.85 | **no** → band |
| D7 | LinkedIn-URL equality (Hack Nation `linkedin_url` == GitHub `socialAccounts` LinkedIn / another source) | 0.97 | yes |
| D8 | Hack Nation project `githubUrl` → GitHub repo → core contributor, name JW≥0.9 | 0.90 | yes |

A PSR ending all stages with no active link → mint a new `person` (UUIDv4).

**Stage 3 — Splink 4.0.16, DuckDB backend, run locally.** Pull PSR via `databricks-sql-connector` → run Splink → write scored pairs back.

```python
import splink.comparison_library as cl
from splink import Linker, DuckDBAPI, SettingsCreator, block_on

settings = SettingsCreator(
    link_type="dedupe_only",           # PSRs from all sources in one frame; 'source' is a feature, not a boundary
    blocking_rules_to_generate_predictions=[
        block_on("last_name"),
        block_on("email_domain"),                          # non-generic domains only
        block_on("substr(first_name,1,1)", "org_norm"),
        "l.github_login = replace(r.name_norm, ' ', '')",  # login ~ concatenated name
    ],
    comparisons=[
        cl.NameComparison("name_norm"),
        cl.EmailComparison("primary_email_norm"),
        cl.ExactMatch("org_norm").configure(term_frequency_adjustments=True),
        cl.ExactMatch("country_code"),
        cl.ArrayIntersectAtSizes("keywords", [3, 1]),
    ],
    retain_intermediate_calculation_columns=True,
)
linker = Linker(psr_df, settings, db_api=DuckDBAPI())
linker.training.estimate_u_using_random_sampling(max_pairs=1e6)
# ...EM training sessions per blocking rule...
scores = linker.inference.predict(threshold_match_probability=0.45)
```

Bands: **≥0.90 auto-link** (`method='splink'`, comparison vector → `evidence`); **0.60–0.90 → Stage 4 LLM adjudication**; **0.45–0.60 → `ops.er_review_queue`**; <0.45 discard.

**Stage 4 — LLM adjudication band (0.60–0.90).** Primary (in-warehouse):

```sql
INSERT INTO ops.llm_adjudications
SELECT pair_id, ai_query(
  'databricks-claude-sonnet-4-6',
  concat('Same real person? Answer strict JSON {"verdict":"match|no_match|unsure",',
         '"rationale":"...","fields_supporting":[...]}. ',
         'Record A: ', to_json(a_fields), ' Record B: ', to_json(b_fields),
         ' Context: A is a ', a_source, ' identity, B is a ', b_source, ' identity.')
) AS verdict_json, current_timestamp()
FROM silver.v_adjudication_pairs;
```

Fallback (if the Free-Edition Claude endpoint is unavailable): Anthropic **Message Batches** with `claude-opus-4-8` (50% batch discount), JSON-schema-constrained output. `match` → link at 0.90 (`method='llm_adjudication'`, rationale into `evidence`); `unsure` → review queue; `no_match` → recorded so re-runs skip re-asking.

**Stage 5 — Survivorship + downstream refresh** (after every wave): rebuild `person` canonical fields with source precedence (identifiers: interview > github > openalex > zefix; name: most complete; affiliation: most recent) → backfill denormalized `person_id` on `contribution`/`authorship`/`officer` → rebuild `person_connection` → mark affected `venture_score.is_latest=false` (rescore trigger). **Conflicting sources are flagged** (e.g., two affiliations) into the memo/review, not silently resolved.

## Quality integration

- **Corroboration**: a fact/edge reaches "high-confidence" (`is_provisional=false`) only with ≥2 independent source types; `corroboration_count` tracked. Single-source and enrichment facts stay provisional and never auto-promote.
- **Golden-set precision**: measured each cycle (target ≥95% precision, false-merge rate tracked) → `ops.data_quality_report`.

## Precision guardrails

1. **Auto-merge floor 0.90**, and *never* on name-similarity alone — an independent identifier (email/ORCID/URL/handle/cross-link) or ≥2 agreeing non-name fields required; D6 (name+org) is deliberately below the floor.
2. **Same-source collision**: linking a 2nd PSR of the same source type to a person (two GitHub accounts) always routes to human review.
3. **Unmerge** (`er/unmerge.py`): retract the wrong link (`status='retracted'`, reason) → mint/re-point to the correct person + corrective link (`method='human_review'`) → re-run survivorship for both → refresh denormalized `person_id` + rebuild affected `person_connection` → invalidate affected `venture_score.is_latest`. **No fact row is ever touched** — the payoff of the PSR pattern.

## Incremental re-runs

Watermark on `person_source_record.ingested_at` (CDF available). Deterministic pass runs on arrival (cheap SQL). Splink: re-run the full pass nightly (seconds at this scale); UUIDv5 link ids + MERGE make re-runs idempotent — they may *add* links, never auto-retract active ones. (`find_matches_to_new_records` exists for true incremental if needed later.)

Expectation at demo: ~60–70% auto-link rate; the interview loop is the designed consent-based backfill.
