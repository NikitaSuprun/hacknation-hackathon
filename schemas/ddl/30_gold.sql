-- 30_gold.sql  (run with ${catalog} = dealflow | dealflow_dev)
USE CATALOG ${catalog};
CREATE SCHEMA IF NOT EXISTS gold;

CREATE TABLE IF NOT EXISTS gold.venture (
  venture_id   STRING NOT NULL,                    -- UUIDv5(ns, anchor_type||':'||anchor_id)
  anchor_type  STRING NOT NULL,                    -- repo | company | paper_cluster | hackathon_project
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
) TBLPROPERTIES (delta.feature.allowColumnDefaults = 'supported');  -- exclude_corporate_oss DEFAULT

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

CREATE TABLE IF NOT EXISTS gold.institution_score (  -- universities + companies -> calibrated 0-100 (home of MIT>KTH)
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

CREATE TABLE IF NOT EXISTS gold.venture_gaps (       -- unfilled fields -> interview question plan
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

CREATE TABLE IF NOT EXISTS gold.score_run (          -- rescore ledger: idempotent trigger handling (WS-E)
  run_id         STRING NOT NULL,
  trigger        STRING NOT NULL,                    -- interview | nightly | ideal_edit | manual
  venture_id     STRING,
  thesis_id      STRING,
  input_versions VARIANT,                            -- content hashes of the inputs the run saw
  status         STRING NOT NULL,                    -- ok | error | skipped_duplicate
  started_at     TIMESTAMP NOT NULL,
  finished_at    TIMESTAMP,
  CONSTRAINT pk_score_run PRIMARY KEY (run_id)
);
