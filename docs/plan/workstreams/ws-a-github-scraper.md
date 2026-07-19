# WS-A — GitHub scraper

**Owner**: 1 dev · **Timing**: ~2.5 days · **Depends on**: WS0 (T0, T3 shared lib).
**Goal**: top ~500 most-starred repos created in a rolling 30-day window → bronze; harvest core contributors, profiles, and commits; collect funded-team signals for downstream exclusion.

**Reference**: [scrapers.md § GitHub](../reference/scrapers.md) · [data-model § bronze](../reference/data-model.md)

## Checklist

- [ ] **G1 — Discovery + hydration**
  - [x] REST Search with created-date bisection (1000-cap workaround; dedupe by `node_id`)
  - [x] GraphQL alias-batch hydration (25 repos/query: metadata, topics, languages, license, homepage, `fundingLinks`, owner type/membership, 100-commit history with `additions/deletions` + author emails)
  - [x] README via REST (`Accept: raw`, truncate 200KB) → `bronze.github_repos_raw`
  - [ ] *Acceptance*: ≥450 distinct repos for the last-30d window; re-run idempotent; rate headroom logged; 20-repo fixture set committed *(fixture set + offline replay tests done; live counts need a PAT + Databricks creds — see run notes below)*
- [ ] **G2 — Contributors / profiles / commits**
  - [x] Bot filter (`type==Bot`, `[bot]`, denylist) + core-contributor rule (`>= max(3, ceil(0.05*total))` AND rank ≤10, cap 5/repo)
  - [x] GraphQL profile batches (50 users/query; incl. `socialAccounts` → self-declared LinkedIn/Twitter)
  - [x] Commit rows with stats + candidate emails (drop `*@users.noreply.github.com`) → `bronze.github_users_raw`, `bronze.github_commits_raw`
  - [ ] *Acceptance*: ~2k users; zero `[bot]` logins harvested; commits carry stats + emails; spot-check 10 repos' core sets *(offline proxies green: zero-bot + email/stat assertions in tests/scrapers/test_github_replay.py; live counts pending)*
- [ ] **G3 — Funded signals + incremental mode**
  - [x] Regex battery + org fields → funded-signal columns; ETag `If-None-Match` cache; sliding-window daily mode
  - [ ] *Acceptance*: planted funded fixture flags ≥2 signals *(green offline)*; daily run <10 min; ≥50% of README/contributor refetches return 304 *(live checks pending)*

## Run notes

- CLI: `uv run python -m scrapers.github [--since YYYY-MM-DD] [--limit N] [--fixtures] [--dry-run]`.
  `--fixtures --dry-run` is the credential-free CI path (replays `scrapers/github/fixtures/`).
- Live runs need `GITHUB_TOKEN` + `SCRAPER_CONTACT_EMAIL` (see `.env.example`) and Databricks creds
  unless `--dry-run`. Commit history is capped at the first 100 commits per repo for now
  (follow-up pagination to ~300 is a known cut).
- ETags live in the `ops.scrape_state` cursor and are mirrored to `bronze.github_repos_raw.etag`;
  rate headroom is logged from `x-ratelimit-*` and the GraphQL `rateLimit` tail.

## Notes & risks
- Single authenticated PAT is enough (verified: backfill ~25–35 min, >2× headroom on every limit). Use per-dev tokens to avoid tripping secondary limits during dev churn; the rate limiter lives in `common/http.py`.
- Everything derived later (person ER, funded classification, star-velocity, team graph) must be recomputable from bronze without re-crawling.
