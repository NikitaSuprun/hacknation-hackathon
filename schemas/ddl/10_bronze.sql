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
