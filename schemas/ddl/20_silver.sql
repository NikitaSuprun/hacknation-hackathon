-- 20_silver.sql  (run with ${catalog} = dealflow | dealflow_dev)
-- Facts attach to per-source identities (person_source_record), never directly to
-- golden persons; golden persons are a reversible set of links.
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
  source            STRING NOT NULL,              -- github | openalex_author | arxiv_author | s2_author | zefix_officer | interview | enrichment | hacknation
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
  venture_likeness  DOUBLE,                         -- 0..1 signal-vs-noise gate (awesome-list/course/dotfiles -> low)
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
  code_urls       ARRAY<STRING>,                   -- paper <-> repo links
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
  purpose            STRING,                       -- Zweck text; feeds problem/market scoring + startup-likeness
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

CREATE TABLE IF NOT EXISTS silver.contribution (     -- person<->repo, keyed on the SOURCE identity
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

CREATE TABLE IF NOT EXISTS silver.authorship (       -- person<->publication
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

CREATE TABLE IF NOT EXISTS silver.officer (          -- person<->company
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
