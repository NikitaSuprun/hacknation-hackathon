-- 40_ops.sql  (run with ${catalog} = dealflow | dealflow_dev)
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

-- Parquet staging area for the merge_upsert write path (tools/db.py).
CREATE VOLUME IF NOT EXISTS ops.staging;

CREATE TABLE IF NOT EXISTS ops.llm_adjudications (   -- stage-4 verdicts; no_match persisted so re-runs skip
  pair_id STRING NOT NULL,                           -- UUIDv5(ns, sorted psr ids)
  source_record_id_a STRING NOT NULL, source_record_id_b STRING NOT NULL,
  splink_probability DOUBLE, verdict STRING NOT NULL, rationale STRING,
  fields_supporting ARRAY<STRING>, model STRING NOT NULL,
  pipeline_version STRING NOT NULL, adjudicated_at TIMESTAMP NOT NULL,
  CONSTRAINT pk_llm_adjudications PRIMARY KEY (pair_id)
);
