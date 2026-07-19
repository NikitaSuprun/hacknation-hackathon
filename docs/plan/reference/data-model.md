# Data model — Unity Catalog DDLs, IDs, join paths

The complete data contract. DDLs are parameterized by catalog (`${catalog}` = `dealflow` | `dealflow_dev`) and applied by `tools/apply_ddl.py`. After the Day-1 freeze, changes are **additive-only** (add nullable columns; never remove/rename).

## Catalog & schema layout

```
dealflow          -- "prod" catalog (live scraped data)
dealflow_dev      -- identical structure, loaded from fixtures; UI/scoring teams build here on day 1
  ├── bronze      -- raw, per-source, payload-preserving, idempotent MERGE targets
  ├── silver      -- resolved entities + relationship facts (the ER contract)
  ├── gold        -- product-facing: ventures, scores, memos, outreach (the UI contract)
  └── ops         -- operational state: cursors, review queue, erasure log, quality report
```

Conventions:
- IDs are `STRING` UUIDs (see below). Every fact row carries `source_url` + `scraped_at` (per-row provenance, non-negotiable).
- Raw payloads are `VARIANT`; because VARIANT is not comparable, change detection uses an explicit `content_hash STRING` (sha256 of canonical JSON), never `payload = payload`.
- `PRIMARY KEY` constraints are Unity Catalog informational; `CHECK` constraints are enforced by Delta (added via `ALTER TABLE`).
- Bronze + `person_source_record` set `delta.enableChangeDataFeed = true` so incremental ER can consume changes. No partitioning/clustering at this scale (~5k persons).
- Quality fields (added by the quality-over-quantity gates): silver facts carry `confidence DOUBLE` + `corroboration_count INT` + `is_provisional BOOLEAN`; `person.data_quality_score`; `venture.quality_tier`.

## ID strategy

Do **not** use unsigned/sequential ints (Spark has no unsigned type; IDENTITY fights idempotent MERGE and differs dev vs prod). Instead:

| Entity | ID | Why |
|---|---|---|
| `person_source_record`, `project`, `publication`, `company`, `venture`, `contribution`, `authorship`, `officer` | **Deterministic UUIDv5** = `uuid5(DEALFLOW_NS, '<entity>:<natural_key>')` | any process computes the same id with zero coordination → MERGE idempotent, fixtures stable everywhere |
| `person` | **Random UUIDv4** | persons have no natural key (that's the ER problem); ids must survive merges/splits |
| `person_source_link` | UUIDv5 of `(person_id, source_record_id, match_method)` | ER re-runs MERGE-dedupe instead of stacking dup links |
| `venture_score`, `memo`, `outreach`, `interview` | UUIDv4 | event-like rows |

`DEALFLOW_NS = uuid5(uuid.NAMESPACE_URL, 'dealflow.hacknation.2026')` — one constant in `tools/ids.py`, the only place IDs are minted. **Merges are never destructive**: merging person B into A retracts B's links, re-issues them against A, sets B `status='merged', merged_into_person_id=A`. Unmerge is the reverse.

---

## Bronze DDLs

```sql
-- 10_bronze.sql  (run with ${catalog} = dealflow | dealflow_dev)
USE CATALOG ${catalog};
CREATE SCHEMA IF NOT EXISTS bronze;

CREATE TABLE IF NOT EXISTS bronze.github_repos_raw (
  repo_id        BIGINT NOT NULL,            -- GitHub numeric id (stable across renames)
  full_name      STRING NOT NULL,
  payload        VARIANT,                    -- full API repo object + README under payload:readme_md
  content_hash   STRING NOT NULL,            -- sha256(canonical payload json) — MERGE no-op skip
  etag           STRING,                     -- GitHub conditional-request cache
  source_url     STRING NOT NULL,
  scraped_at     TIMESTAMP NOT NULL,
  ingested_at    TIMESTAMP NOT NULL,
  scrape_run_id  STRING NOT NULL,
  CONSTRAINT pk_github_repos_raw PRIMARY KEY (repo_id)
) TBLPROPERTIES (delta.enableChangeDataFeed = true);

CREATE TABLE IF NOT EXISTS bronze.github_users_raw (
  user_id        BIGINT NOT NULL,
  login          STRING NOT NULL,
  payload        VARIANT,                    -- /users/{login}: name, company, blog, email, twitter, bio, location, avatar_url, socialAccounts
  content_hash   STRING NOT NULL,
  source_url     STRING NOT NULL,
  scraped_at     TIMESTAMP NOT NULL,
  ingested_at    TIMESTAMP NOT NULL,
  scrape_run_id  STRING NOT NULL,
  CONSTRAINT pk_github_users_raw PRIMARY KEY (user_id)
) TBLPROPERTIES (delta.enableChangeDataFeed = true);

CREATE TABLE IF NOT EXISTS bronze.github_commits_raw (
  repo_id        BIGINT NOT NULL,
  sha            STRING NOT NULL,
  author_user_id BIGINT,                     -- GitHub-linked author (null if unlinked email-only)
  payload        VARIANT,                    -- commit object: author {name,email,date}, committer, message, stats
  source_url     STRING NOT NULL,
  scraped_at     TIMESTAMP NOT NULL,
  ingested_at    TIMESTAMP NOT NULL,
  scrape_run_id  STRING NOT NULL,
  CONSTRAINT pk_github_commits_raw PRIMARY KEY (repo_id, sha)
) TBLPROPERTIES (delta.enableChangeDataFeed = true);

CREATE TABLE IF NOT EXISTS bronze.arxiv_papers_raw (
  arxiv_id       STRING NOT NULL,            -- base id, no version: '2506.01234'
  latest_version INT,
  payload        VARIANT,                    -- Atom entry as JSON (title, abstract, authors[], categories, links, comment)
  content_hash   STRING NOT NULL,
  source_url     STRING NOT NULL,
  scraped_at     TIMESTAMP NOT NULL,
  ingested_at    TIMESTAMP NOT NULL,
  scrape_run_id  STRING NOT NULL,
  CONSTRAINT pk_arxiv_papers_raw PRIMARY KEY (arxiv_id)
) TBLPROPERTIES (delta.enableChangeDataFeed = true);

CREATE TABLE IF NOT EXISTS bronze.openalex_works_raw (
  openalex_id    STRING NOT NULL,            -- 'W...'
  doi            STRING,
  arxiv_id       STRING,                     -- promoted for the join spine
  payload        VARIANT,                    -- authorships[] with author ids (A...), ORCID, institutions (ROR)
  content_hash   STRING NOT NULL,
  source_url     STRING NOT NULL,
  scraped_at     TIMESTAMP NOT NULL,
  ingested_at    TIMESTAMP NOT NULL,
  scrape_run_id  STRING NOT NULL,
  CONSTRAINT pk_openalex_works_raw PRIMARY KEY (openalex_id)
) TBLPROPERTIES (delta.enableChangeDataFeed = true);

CREATE TABLE IF NOT EXISTS bronze.s2_papers_raw (      -- Semantic Scholar enrichment (optional in MVP)
  s2_id          STRING NOT NULL,
  arxiv_id       STRING,
  doi            STRING,
  payload        VARIANT,
  content_hash   STRING NOT NULL,
  source_url     STRING NOT NULL,
  scraped_at     TIMESTAMP NOT NULL,
  ingested_at    TIMESTAMP NOT NULL,
  scrape_run_id  STRING NOT NULL,
  CONSTRAINT pk_s2_papers_raw PRIMARY KEY (s2_id)
) TBLPROPERTIES (delta.enableChangeDataFeed = true);

CREATE TABLE IF NOT EXISTS bronze.paper_code_links (   -- one-time load of the PwC archive (HF pwc-archive)
  paper_arxiv_id STRING,
  repo_url       STRING NOT NULL,
  is_official    BOOLEAN,
  mentioned_in_paper BOOLEAN,
  source_url     STRING NOT NULL,
  ingested_at    TIMESTAMP NOT NULL,
  CONSTRAINT pk_paper_code_links PRIMARY KEY (repo_url, paper_arxiv_id)
);

CREATE TABLE IF NOT EXISTS bronze.zefix_companies_raw (
  uid            STRING NOT NULL,            -- 'CHE-123.456.789'
  name           STRING NOT NULL,
  payload        VARIANT,                    -- PublicREST company detail (purpose, legalForm, sogcPub, address)
  content_hash   STRING NOT NULL,
  source_url     STRING NOT NULL,
  scraped_at     TIMESTAMP NOT NULL,
  ingested_at    TIMESTAMP NOT NULL,
  scrape_run_id  STRING NOT NULL,
  CONSTRAINT pk_zefix_companies_raw PRIMARY KEY (uid)
) TBLPROPERTIES (delta.enableChangeDataFeed = true);

CREATE TABLE IF NOT EXISTS bronze.zefix_sogc_raw (     -- SOGC/SHAB publications: officer mutations + capital-increase signals
  sogc_id        STRING NOT NULL,
  uid            STRING,
  published_date DATE,
  sub_rubric     STRING,                     -- HR01 new / HR02 mutation / HR03 deletion
  payload        VARIANT,                    -- publication incl. "Eingetragene Personen" text + capital changes
  content_hash   STRING NOT NULL,
  source_url     STRING NOT NULL,
  scraped_at     TIMESTAMP NOT NULL,
  ingested_at    TIMESTAMP NOT NULL,
  scrape_run_id  STRING NOT NULL,
  CONSTRAINT pk_zefix_sogc_raw PRIMARY KEY (sogc_id)
) TBLPROPERTIES (delta.enableChangeDataFeed = true);

CREATE TABLE IF NOT EXISTS bronze.hacknation_people_raw (  -- Hack Nation showcase participants (public JSON API)
  user_id        STRING NOT NULL,
  payload        VARIANT,                    -- bff-public-people-v2 person object
  content_hash   STRING NOT NULL,
  source_url     STRING NOT NULL,
  scraped_at     TIMESTAMP NOT NULL,
  ingested_at    TIMESTAMP NOT NULL,
  scrape_run_id  STRING NOT NULL,
  CONSTRAINT pk_hacknation_people_raw PRIMARY KEY (user_id)
) TBLPROPERTIES (delta.enableChangeDataFeed = true);

CREATE TABLE IF NOT EXISTS bronze.hacknation_projects_raw ( -- Hack Nation projects (team, githubUrl, structured pitch)
  project_id     STRING NOT NULL,
  payload        VARIANT,                    -- bff-projects-public-v2 detail (authorProfile, team[], githubUrl, structured)
  content_hash   STRING NOT NULL,
  source_url     STRING NOT NULL,
  scraped_at     TIMESTAMP NOT NULL,
  ingested_at    TIMESTAMP NOT NULL,
  scrape_run_id  STRING NOT NULL,
  CONSTRAINT pk_hacknation_projects_raw PRIMARY KEY (project_id)
) TBLPROPERTIES (delta.enableChangeDataFeed = true);

CREATE TABLE IF NOT EXISTS bronze._rejects (           -- validation failures never crash a run; they land here
  source STRING, natural_key STRING, error STRING, raw STRING, scrape_run_id STRING, ingested_at TIMESTAMP
);
```

**Minimization at ingest**: the Zefix parser drops place-of-origin (`Heimatort`) and private home addresses before writing `payload`.

---

## Silver DDLs — identity model

Core pattern: **facts attach to per-source identities (`person_source_record`), never directly to golden persons.** Golden persons are a reversible set of links, so ER mistakes are corrected by link surgery without touching fact rows. Denormalized `person_id` columns on fact tables are a refreshable cache, not the source of truth.

```sql
-- 20_silver.sql
USE CATALOG ${catalog};
CREATE SCHEMA IF NOT EXISTS silver;

CREATE TABLE IF NOT EXISTS silver.person (          -- golden record; survivorship-derived from linked PSRs
  person_id             STRING NOT NULL,            -- UUIDv4, minted once, never reused
  full_name             STRING,
  display_name          STRING,
  primary_email         STRING,
  emails                ARRAY<STRING>,              -- all observed professional emails (no noreply)
  github_login          STRING,
  orcid                 STRING,
  website_url           STRING,                     -- personal site/portfolio (enrichment source)
  linkedin_url          STRING,                     -- pointer only; investor click-through
  cv_url                STRING,                     -- pointer (e.g. Hack Nation cvUrl); content parsing gated by legal sign-off
  twitter_handle        STRING,
  affiliation           STRING,                     -- current best org guess
  location              STRING,
  country_code          STRING,
  headline              STRING,                     -- 1-line AI-synthesized professional summary
  avatar_url            STRING,                     -- UI display only; no image analysis by default
  data_quality_score    DOUBLE,                     -- 0..1 completeness/corroboration/freshness
  status                STRING NOT NULL,            -- active | merged | erased
  merged_into_person_id STRING,
  created_at            TIMESTAMP NOT NULL,
  updated_at            TIMESTAMP NOT NULL,
  CONSTRAINT pk_person PRIMARY KEY (person_id)
);
ALTER TABLE silver.person ADD CONSTRAINT chk_person_status CHECK (status IN ('active','merged','erased'));

CREATE TABLE IF NOT EXISTS silver.person_source_record (  -- immutable per-source identity; ER input
  source_record_id  STRING NOT NULL,              -- UUIDv5(ns, source || ':' || source_key)
  source            STRING NOT NULL,              -- github | openalex_author | arxiv_author | s2_author | zefix_officer | interview | enrichment
  source_key        STRING NOT NULL,
  bronze_ref        STRING,                       -- e.g. 'bronze.github_users_raw:user_id=123'
  full_name         STRING,
  name_norm         STRING,                       -- lower, de-accented, titles stripped
  first_name        STRING,
  last_name         STRING,
  emails            ARRAY<STRING>,
  email_norms       ARRAY<STRING>,                -- lowered, noreply/generic excluded
  email_domain      STRING,                       -- blocking key
  orcid             STRING,
  github_login      STRING,
  website_url_norm  STRING,
  linkedin_url      STRING,
  twitter_handle    STRING,
  affiliation_raw   STRING,
  org_norm          STRING,                       -- legal suffixes stripped, uni aliases folded
  location_raw      STRING,
  country_code      STRING,
  keywords          ARRAY<STRING>,
  bio               STRING,
  source_url        STRING NOT NULL,
  first_seen_at     TIMESTAMP NOT NULL,
  last_seen_at      TIMESTAMP NOT NULL,
  scraped_at        TIMESTAMP NOT NULL,
  ingested_at       TIMESTAMP NOT NULL,
  CONSTRAINT pk_psr PRIMARY KEY (source_record_id)
) TBLPROPERTIES (delta.enableChangeDataFeed = true);

CREATE TABLE IF NOT EXISTS silver.person_source_link (  -- the ER decisions; append-only, reversible
  link_id           STRING NOT NULL,              -- UUIDv5(ns, person_id||source_record_id||match_method)
  person_id         STRING NOT NULL,
  source_record_id  STRING NOT NULL,
  match_confidence  DOUBLE NOT NULL,              -- 0..1
  match_method      STRING NOT NULL,              -- det_email | det_orcid | det_website | det_handle | det_crosslink | splink | llm_adjudication | human_review | interview_claim | seed_fixture
  evidence          VARIANT,
  pipeline_version  STRING NOT NULL,
  matched_at        TIMESTAMP NOT NULL,
  status            STRING NOT NULL,              -- active | retracted
  retracted_at      TIMESTAMP,
  retracted_by      STRING,
  retracted_reason  STRING,
  CONSTRAINT pk_psl PRIMARY KEY (link_id)
);
ALTER TABLE silver.person_source_link ADD CONSTRAINT chk_psl_status CHECK (status IN ('active','retracted'));
ALTER TABLE silver.person_source_link ADD CONSTRAINT chk_psl_conf CHECK (match_confidence BETWEEN 0 AND 1);
-- Invariant enforced by the ER job (not a Delta constraint): at most ONE active link per source_record_id.

CREATE TABLE IF NOT EXISTS silver.project (          -- GitHub repo as a signal artifact
  project_id        STRING NOT NULL,               -- UUIDv5(ns,'github_repo:'||repo_id)
  repo_id           BIGINT NOT NULL,
  full_name         STRING NOT NULL,
  name              STRING,
  owner_login       STRING,
  is_org_owned      BOOLEAN,
  description       STRING,
  summary_ai        STRING,
  market_tags       ARRAY<STRING>,
  usp_notes         STRING,
  primary_language  STRING,
  languages         MAP<STRING,BIGINT>,
  topics            ARRAY<STRING>,
  stars             INT, forks INT,
  license           STRING,
  homepage_url      STRING,
  source_platform   STRING,                         -- github | hacknation
  github_url        STRING,                         -- for hacknation projects (the ER spine, rule D8)
  structured        VARIANT,                        -- hacknation pitch {problem,solution,usp,impact,implementation,targetAudience}
  event_title       STRING, challenge_title STRING, -- hacknation hackathon + challenge
  is_winner         BOOLEAN,
  arxiv_ids_in_readme ARRAY<STRING>,
  funding_signals   ARRAY<STRING>,                 -- regex/LLM hits: "backed by", sponsors, YC, etc.
  is_corporate_oss  BOOLEAN,
  is_academic       BOOLEAN,
  venture_likeness  DOUBLE,                         -- 0..1 signal-vs-noise gate (awesome-list/course/dotfiles → low)
  contributor_count INT,
  created_at_source TIMESTAMP,
  pushed_at         TIMESTAMP,
  ai_model_version  STRING,
  source_url        STRING NOT NULL,
  scraped_at        TIMESTAMP NOT NULL,
  updated_at        TIMESTAMP NOT NULL,
  CONSTRAINT pk_project PRIMARY KEY (project_id)
);

CREATE TABLE IF NOT EXISTS silver.publication (      -- unified work: arXiv spine + OpenAlex/S2 enrichment
  publication_id  STRING NOT NULL,                 -- UUIDv5(ns, coalesce(doi,'arxiv:'||arxiv_id, openalex_id))
  doi             STRING,
  arxiv_id        STRING,
  openalex_id     STRING,
  s2_id           STRING,
  title           STRING NOT NULL,
  abstract        STRING,
  published_at    DATE,
  venue           STRING,
  primary_source  STRING NOT NULL,                 -- data_source discriminator: arxiv | openalex | s2
  sources         ARRAY<STRING> NOT NULL,
  concepts        ARRAY<STRING>,
  code_urls       ARRAY<STRING>,                   -- paper ↔ repo links
  citation_count  INT,
  is_preprint     BOOLEAN,
  source_extras   VARIANT,                         -- source-specific fields (arxiv comment/primary_category; thesis advisor/degree)
  source_url      STRING NOT NULL,
  scraped_at      TIMESTAMP NOT NULL,
  updated_at      TIMESTAMP NOT NULL,
  CONSTRAINT pk_publication PRIMARY KEY (publication_id)
);

CREATE TABLE IF NOT EXISTS silver.company (          -- Zefix
  company_id         STRING NOT NULL,              -- UUIDv5(ns,'zefix:'||uid)
  uid                STRING NOT NULL,
  name               STRING NOT NULL,
  legal_form         STRING,
  legal_seat         STRING,
  canton             STRING,
  address_street     STRING,                       -- business/registered office only
  address_zip        STRING,
  address_town       STRING,
  purpose            STRING,                       -- Zweck text — feeds problem/market scoring + startup-likeness
  startup_likeness   STRING,                       -- tech_startup_candidate | traditional | holding_shell | other
  status             STRING,                       -- ACTIVE | CANCELLED ...
  incorporation_date DATE,
  website_url        STRING,
  first_sogc_id      STRING,
  source_url         STRING NOT NULL,
  scraped_at         TIMESTAMP NOT NULL,
  updated_at         TIMESTAMP NOT NULL,
  CONSTRAINT pk_company PRIMARY KEY (company_id)
);

CREATE TABLE IF NOT EXISTS silver.contribution (     -- person↔repo, keyed on the SOURCE identity
  contribution_id   STRING NOT NULL,               -- UUIDv5(ns, project_id||source_record_id)
  project_id        STRING NOT NULL,
  source_record_id  STRING NOT NULL,               -- github PSR (stable under ER changes)
  person_id         STRING,                        -- denormalized cache; JOIN via link table is truth
  commit_count      INT,
  additions         BIGINT,
  deletions         BIGINT,
  sample_commit_shas ARRAY<STRING>,
  commit_emails     ARRAY<STRING>,                 -- ER fuel
  languages         ARRAY<STRING>,
  first_commit_at   TIMESTAMP,
  last_commit_at    TIMESTAMP,
  contribution_share DOUBLE,
  confidence        DOUBLE, corroboration_count INT, is_provisional BOOLEAN,
  computed_at       TIMESTAMP NOT NULL,
  source_url        STRING NOT NULL,
  CONSTRAINT pk_contribution PRIMARY KEY (contribution_id)
);

CREATE TABLE IF NOT EXISTS silver.authorship (       -- person↔publication
  authorship_id     STRING NOT NULL,               -- UUIDv5(ns, publication_id||source_record_id)
  publication_id    STRING NOT NULL,
  source_record_id  STRING NOT NULL,
  person_id         STRING,
  author_position   INT,
  is_last_author    BOOLEAN,                        -- PI signal
  raw_author_name   STRING,
  affiliation_raw   STRING,
  confidence        DOUBLE, corroboration_count INT, is_provisional BOOLEAN,
  source_url        STRING NOT NULL,
  updated_at        TIMESTAMP NOT NULL,
  CONSTRAINT pk_authorship PRIMARY KEY (authorship_id)
);

CREATE TABLE IF NOT EXISTS silver.officer (          -- person↔company
  officer_id        STRING NOT NULL,               -- UUIDv5(ns, company_id||source_record_id||role_norm)
  company_id        STRING NOT NULL,
  source_record_id  STRING NOT NULL,
  person_id         STRING,
  role              STRING,                         -- as registered
  role_norm         STRING,                         -- founder | board | md | signatory | other
  signing_authority STRING,
  registered_at     DATE,
  deregistered_at   DATE,
  evidence_sogc_id  STRING,
  confidence        DOUBLE, corroboration_count INT, is_provisional BOOLEAN,
  source_url        STRING NOT NULL,
  updated_at        TIMESTAMP NOT NULL,
  CONSTRAINT pk_officer PRIMARY KEY (officer_id)
);

CREATE TABLE IF NOT EXISTS silver.person_connection ( -- collaboration graph, edge table
  person_a_id     STRING NOT NULL,                  -- invariant: person_a_id < person_b_id
  person_b_id     STRING NOT NULL,
  connection_type STRING NOT NULL,                  -- coauthor | co_contributor | co_officer
  weight          DOUBLE NOT NULL,                  -- shared-artifact count with recency decay
  evidence        ARRAY<STRING>,                    -- shared publication_ids / project_ids / company_ids
  first_seen      DATE,
  last_seen       DATE,
  updated_at      TIMESTAMP NOT NULL,
  CONSTRAINT pk_person_connection PRIMARY KEY (person_a_id, person_b_id, connection_type)
);
ALTER TABLE silver.person_connection ADD CONSTRAINT chk_conn_type CHECK (connection_type IN ('coauthor','co_contributor','co_officer'));
ALTER TABLE silver.person_connection ADD CONSTRAINT chk_conn_order CHECK (person_a_id < person_b_id);
```

**Why an edge table, not a `people_connected` array inside `person`**: arrays can't carry per-edge type/weight/evidence, cause write amplification (every new collaboration rewrites person rows), and go stale after merges. The UI still gets a sorted array via `gold.v_person_network` (one `sort_array(collect_list(...))`).

---

## Gold DDLs — product surface

```sql
-- 30_gold.sql
USE CATALOG ${catalog};
CREATE SCHEMA IF NOT EXISTS gold;

CREATE TABLE IF NOT EXISTS gold.venture (
  venture_id   STRING NOT NULL,                    -- UUIDv5(ns, anchor_type||':'||anchor_id)
  anchor_type  STRING NOT NULL,                    -- repo | company | paper_cluster
  anchor_id    STRING NOT NULL,
  name         STRING NOT NULL,
  one_liner    STRING,
  summary_ai   STRING,
  market_tags  ARRAY<STRING>,
  website_url  STRING,
  quality_tier STRING,                             -- scored | needs_more_data (quality gate into the pool)
  status       STRING NOT NULL,                    -- sourced | scored | shortlisted | outreach | interviewing | passed | archived
  created_at   TIMESTAMP NOT NULL,
  updated_at   TIMESTAMP NOT NULL,
  CONSTRAINT pk_venture PRIMARY KEY (venture_id)
);
ALTER TABLE gold.venture ADD CONSTRAINT chk_venture_anchor CHECK (anchor_type IN ('repo','company','paper_cluster','hackathon_project'));
ALTER TABLE gold.venture ADD CONSTRAINT chk_venture_status CHECK (status IN ('sourced','scored','shortlisted','outreach','interviewing','passed','archived'));

CREATE TABLE IF NOT EXISTS gold.venture_member (
  venture_id       STRING NOT NULL,
  person_id        STRING NOT NULL,
  role_hint        STRING,                          -- founder | maintainer | author | officer | unknown
  is_founder_guess BOOLEAN,
  weight           DOUBLE,                          -- contribution share / credit
  evidence         VARIANT,
  added_by         STRING NOT NULL,                 -- pipeline | analyst
  added_at         TIMESTAMP NOT NULL,
  CONSTRAINT pk_venture_member PRIMARY KEY (venture_id, person_id)
);

CREATE TABLE IF NOT EXISTS gold.thesis (             -- VC inputs, editable in UI
  thesis_id     STRING NOT NULL,
  name          STRING NOT NULL,
  owner_email   STRING,
  sectors       ARRAY<STRING>,
  geographies   ARRAY<STRING>,
  stages        ARRAY<STRING>,                      -- pre-seed | seed | ...
  check_size_min_chf BIGINT,
  check_size_max_chf BIGINT,
  require_no_prior_vc BOOLEAN,
  min_team INT, max_team INT,
  exclude_corporate_oss BOOLEAN DEFAULT true,
  notes         STRING,
  is_active     BOOLEAN NOT NULL,
  updated_by    STRING,
  updated_at    TIMESTAMP NOT NULL,
  CONSTRAINT pk_thesis PRIMARY KEY (thesis_id)
);

CREATE TABLE IF NOT EXISTS gold.candidate_pool (     -- materialized per thesis
  thesis_id       STRING NOT NULL,
  venture_id      STRING NOT NULL,
  included        BOOLEAN NOT NULL,
  exclusion_reasons ARRAY<STRING>,
  funding_signal  STRING,                           -- none_found | suspected | confirmed_funded
  pool_built_at   TIMESTAMP NOT NULL,
  CONSTRAINT pk_candidate_pool PRIMARY KEY (thesis_id, venture_id)
);

CREATE TABLE IF NOT EXISTS gold.ideal_candidate (    -- editable profile + embedding; versioned
  profile_id      STRING NOT NULL,
  thesis_id       STRING NOT NULL,
  version         INT NOT NULL,
  profile_json    VARIANT NOT NULL,                 -- structured editable profile incl. numeric_features
  profile_text    STRING NOT NULL,                  -- deterministic rendering for the domain-fit embedding
  embedding       ARRAY<FLOAT>,                     -- 1024-dim, L2-normalized
  embedding_model STRING,
  is_active       BOOLEAN NOT NULL,
  updated_by      STRING,
  updated_at      TIMESTAMP NOT NULL,
  CONSTRAINT pk_ideal_candidate PRIMARY KEY (profile_id)
);

CREATE TABLE IF NOT EXISTS gold.institution_score (  -- universities + companies → calibrated 0-100 (home of MIT>KTH)
  institution_id  STRING NOT NULL,                  -- UUIDv5 of ROR / canonical name
  kind            STRING NOT NULL,                  -- university | company
  canonical_name  STRING NOT NULL,
  aliases         ARRAY<STRING>,
  ror_id          STRING,
  prestige        DOUBLE,                           -- 0..1 (Leiden CC0 for unis; curated tiers for companies)
  outcome         DOUBLE,                           -- 0..1 founder-production density
  score           DOUBLE NOT NULL,                  -- 0..100 blended
  provenance      VARIANT,
  updated_at      TIMESTAMP NOT NULL,
  CONSTRAINT pk_institution_score PRIMARY KEY (institution_id)
);
ALTER TABLE gold.institution_score ADD CONSTRAINT chk_inst_kind CHECK (kind IN ('university','company'));

CREATE TABLE IF NOT EXISTS gold.score_weights (      -- explicit columns = hard UI contract for 8+1 categories
  weights_id    STRING NOT NULL,
  thesis_id     STRING NOT NULL,
  version       INT NOT NULL,
  w_individual_experience DOUBLE NOT NULL,
  w_schools               DOUBLE NOT NULL,
  w_network_ties          DOUBLE NOT NULL,
  w_prior_collaboration   DOUBLE NOT NULL,
  w_problem_realness      DOUBLE NOT NULL,
  w_product_defensibility DOUBLE NOT NULL,
  w_market                DOUBLE NOT NULL,
  w_traction              DOUBLE NOT NULL,
  w_ideal_match           DOUBLE NOT NULL,          -- weight of the structured ideal-candidate match
  is_active     BOOLEAN NOT NULL,
  updated_by    STRING,
  updated_at    TIMESTAMP NOT NULL,
  CONSTRAINT pk_score_weights PRIMARY KEY (weights_id)
);

CREATE TABLE IF NOT EXISTS gold.venture_score (      -- append-only history; UI reads is_latest
  score_id      STRING NOT NULL,                    -- UUIDv4
  venture_id    STRING NOT NULL,
  thesis_id     STRING NOT NULL,
  weights_id    STRING NOT NULL,
  profile_id    STRING,
  scored_at     TIMESTAMP NOT NULL,
  model_version STRING NOT NULL,
  s_individual_experience DOUBLE,                   -- all 0-100
  s_schools               DOUBLE,
  s_network_ties          DOUBLE,
  s_prior_collaboration   DOUBLE,
  s_problem_realness      DOUBLE,
  s_product_defensibility DOUBLE,
  s_market                DOUBLE,
  s_traction              DOUBLE,
  ideal_match   DOUBLE,                             -- structured feature-space match, 0-100
  final_score   DOUBLE NOT NULL,                    -- weighted sum, precomputed for sorting
  confidence    DOUBLE NOT NULL,                    -- 0..1 data-coverage
  breakdown     VARIANT,                            -- per category {score, method, rationale, evidence:[{claim, source_url}]}
  is_latest     BOOLEAN NOT NULL,
  CONSTRAINT pk_venture_score PRIMARY KEY (score_id)
);
ALTER TABLE gold.venture_score ADD CONSTRAINT chk_conf CHECK (confidence BETWEEN 0 AND 1);

CREATE TABLE IF NOT EXISTS gold.person_features (
  person_id         STRING NOT NULL,
  features          MAP<STRING,DOUBLE>,             -- named numeric features (see scoring-and-memo.md)
  profile_text      STRING,                         -- deterministic "what they build/research" text
  profile_embedding ARRAY<FLOAT>,                   -- 1024-dim, L2-normalized (domain-fit only)
  embedding_model   STRING,
  computed_at       TIMESTAMP NOT NULL,
  CONSTRAINT pk_person_features PRIMARY KEY (person_id)
);

CREATE TABLE IF NOT EXISTS gold.venture_gaps (       -- unfilled fields → interview question plan
  venture_id   STRING NOT NULL,
  field        STRING NOT NULL,
  category     STRING,
  question_text STRING,
  importance   DOUBLE,
  created_at   TIMESTAMP NOT NULL,
  CONSTRAINT pk_venture_gaps PRIMARY KEY (venture_id, field)
);

CREATE TABLE IF NOT EXISTS gold.memo (               -- one live memo per venture, fixed sections
  memo_id       STRING NOT NULL,
  venture_id    STRING NOT NULL,
  thesis_id     STRING,
  run_id        STRING,
  sections      VARIANT NOT NULL,                   -- fixed 9 sections; each bullet {text, evidence:[{source_url}], missing, gap_field}
  model_version STRING NOT NULL,
  generated_at  TIMESTAMP NOT NULL,
  status        STRING NOT NULL,                    -- draft | reviewed | final
  is_latest     BOOLEAN NOT NULL,
  CONSTRAINT pk_memo PRIMARY KEY (memo_id)
);

CREATE TABLE IF NOT EXISTS gold.outreach (           -- consent-based contact; explicit status machine
  outreach_id   STRING NOT NULL,
  venture_id    STRING NOT NULL,
  thesis_id     STRING,
  person_id     STRING NOT NULL,
  channel       STRING NOT NULL,                    -- 'email'
  to_email      STRING,
  subject       STRING,
  body          STRING,
  token_hash    STRING,                             -- sha256 of the single-use interview token
  token_expires_at TIMESTAMP,
  question_plan VARIANT,
  status        STRING NOT NULL,
  consent_at    TIMESTAMP,                          -- REQUIRED before any interview row
  sent_at       TIMESTAMP,
  last_event_at TIMESTAMP,
  history       ARRAY<STRUCT<state:STRING, ts:TIMESTAMP, actor:STRING>>,
  created_by    STRING,
  updated_at    TIMESTAMP NOT NULL,
  CONSTRAINT pk_outreach PRIMARY KEY (outreach_id)
);
ALTER TABLE gold.outreach ADD CONSTRAINT chk_outreach_status
  CHECK (status IN ('draft','approved','sent','bounced','replied','consented','declined','interview_scheduled','interview_started','interviewed','closed','opted_out','expired'));

CREATE TABLE IF NOT EXISTS gold.interview (          -- consent-gated; fills gaps; triggers rescore
  interview_id     STRING NOT NULL,
  outreach_id      STRING NOT NULL,
  venture_id       STRING NOT NULL,
  person_id        STRING NOT NULL,
  consent_confirmed BOOLEAN NOT NULL,
  started_at       TIMESTAMP,
  completed_at     TIMESTAMP,
  transcript       VARIANT,                         -- [{role, text, at}]
  extracted        VARIANT,                         -- education[], career[], team_commitment, traction_claims[], funding_status
  model_version    STRING,
  rescore_score_id STRING,
  updated_at       TIMESTAMP NOT NULL,
  CONSTRAINT pk_interview PRIMARY KEY (interview_id)
);
```

Career history & schools live in `interview.extracted` (consent) + whatever appears in public sources; there is deliberately no scraped `person.education` table.

---

## Ops DDLs

```sql
-- 40_ops.sql
USE CATALOG ${catalog};
CREATE SCHEMA IF NOT EXISTS ops;

CREATE TABLE IF NOT EXISTS ops.scrape_state (
  source STRING NOT NULL, cursor VARIANT, last_run_at TIMESTAMP, last_status STRING,
  last_error STRING, items_upserted BIGINT, updated_at TIMESTAMP NOT NULL,
  CONSTRAINT pk_scrape_state PRIMARY KEY (source)
);

CREATE TABLE IF NOT EXISTS ops.er_review_queue (
  review_id STRING NOT NULL, source_record_id STRING NOT NULL, candidate_person_id STRING NOT NULL,
  score DOUBLE NOT NULL, method STRING NOT NULL, features VARIANT, status STRING NOT NULL,
  decided_by STRING, decided_at TIMESTAMP, created_at TIMESTAMP NOT NULL,
  CONSTRAINT pk_er_review PRIMARY KEY (review_id)
);

CREATE TABLE IF NOT EXISTS ops.llm_run_log (         -- spend + reproducibility tracking
  run_id STRING, stage STRING, model STRING, input_tokens BIGINT, output_tokens BIGINT,
  searches INT, cost_usd DOUBLE, at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ops.data_quality_report ( -- per-cycle quality metrics
  cycle_id STRING, source STRING, reject_rate DOUBLE, er_precision DOUBLE, false_merge_rate DOUBLE,
  coverage DOUBLE, confidence_p50 DOUBLE, freshness_days DOUBLE, computed_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ops.erasure_log (
  erasure_id STRING NOT NULL, person_id STRING NOT NULL, requested_at TIMESTAMP NOT NULL,
  requester_hash STRING, scope STRING NOT NULL, executed_at TIMESTAMP, executed_by STRING,
  rows_deleted VARIANT, vacuum_after TIMESTAMP, notes STRING,
  CONSTRAINT pk_erasure_log PRIMARY KEY (erasure_id)
);

CREATE TABLE IF NOT EXISTS ops.erasure_suppression (  -- blocks re-scrape resurrection
  source STRING NOT NULL, source_key_hash STRING NOT NULL, created_at TIMESTAMP NOT NULL,
  CONSTRAINT pk_erasure_suppression PRIMARY KEY (source, source_key_hash)
);
```

---

## Read views (the UI/proxy contract — UI never reads base tables)

```sql
-- 50_views.sql
CREATE OR REPLACE VIEW gold.v_ranked_ventures AS
SELECT v.venture_id, v.name, v.one_liner, v.status, v.quality_tier, v.market_tags,
       s.final_score, s.confidence, s.ideal_match,
       s.s_individual_experience, s.s_schools, s.s_network_ties, s.s_prior_collaboration,
       s.s_problem_realness, s.s_product_defensibility, s.s_market, s.s_traction,
       s.breakdown, s.scored_at
FROM gold.venture v
LEFT JOIN gold.venture_score s ON s.venture_id = v.venture_id AND s.is_latest;

CREATE OR REPLACE VIEW gold.v_venture_team AS
SELECT vm.venture_id, p.person_id, p.full_name, p.headline, p.github_login, p.orcid,
       p.linkedin_url, p.affiliation, p.avatar_url, vm.role_hint, vm.is_founder_guess, vm.weight, vm.evidence
FROM gold.venture_member vm JOIN silver.person p USING (person_id)
WHERE p.status = 'active';

CREATE OR REPLACE VIEW gold.v_person_network AS      -- the sorted "people_connected" array the UI wants
SELECT person_id,
       sort_array(collect_list(struct(weight, other_person_id, connection_type)), false) AS people_connected
FROM (
  SELECT person_a_id AS person_id, person_b_id AS other_person_id, connection_type, weight FROM silver.person_connection
  UNION ALL
  SELECT person_b_id, person_a_id, connection_type, weight FROM silver.person_connection
) GROUP BY person_id;

CREATE OR REPLACE VIEW gold.v_person_similarity AS   -- SQL dot product (unit vectors) vs the active ideal
SELECT pf.person_id, ic.profile_id,
       aggregate(zip_with(pf.profile_embedding, ic.embedding, (x,y) -> CAST(x*y AS DOUBLE)), 0D, (a,b)->a+b) AS domain_fit
FROM gold.person_features pf CROSS JOIN gold.ideal_candidate ic
WHERE ic.is_active AND pf.profile_embedding IS NOT NULL;
-- gold.v_person_signals: UNION of contribution/authorship/officer joined via active links (see entity-resolution.md).
```

## Canonical join paths (put verbatim in `docs/contract.md`)

```sql
-- 1) All signals for person X → gold.v_person_signals WHERE person_id = :x
--    person → person_source_link(active) → person_source_record → {contribution|authorship|officer} → artifact
-- 2) The team behind venture Y → gold.v_venture_team WHERE venture_id = :y
--    venture → venture_member → person  (venture_member built by the venture-builder job)
-- 3) Who collaborated with whom → silver.person_connection self-joins of fact tables on the shared artifact
```
