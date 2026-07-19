# Scrapers & shared runner framework

Three source scrapers write to Databricks bronze via a shared framework. Each is independently ownable ([WS-A](../workstreams/ws-a-github-scraper.md), [WS-B](../workstreams/ws-b-papers-scraper.md), [WS-C](../workstreams/ws-c-zefix-scraper.md)) after a half-day shared-lib task. All facts verified 2026-07-19.

## Shared runner framework

Monorepo (`uv` + `pyproject.toml`):
```
scrapers/
  common/    base.py (BaseScraper), sink.py (Databricks writer), state.py,
             http.py (retry+ratelimit session), log.py (structlog JSON), cli.py, fixtures.py
  github/    __main__.py, client_rest.py, client_gql.py, models.py, normalize.py, fixtures/*.json
  papers/    __main__.py, arxiv_client.py, openalex_client.py, s2_client.py, models.py, fixtures/
  zefix/     __main__.py, zefix_client.py, shab_client.py, extract_llm.py, models.py, fixtures/
```

**BaseScraper contract**: `run(since, fixtures, dry_run)` → read cursor from `ops.scrape_state` → `fetch(cursor)` yields raw batches → `normalize(raw)` → pydantic v2 models (validation failures → `bronze._rejects`, never crash) → `sink.upsert(table, records, keys)` (idempotent MERGE) → advance cursor only after a successful write. At-least-once fetch + idempotent MERGE ⇒ effectively exactly-once. Retries via `tenacity` (exp backoff + jitter, honor `Retry-After`, max 5); per-source token-bucket rate limiter; structured JSON logs + a run-summary row.

**Write path** (decision): stage a Parquet file to a UC Volume (`databricks-sdk` `files.upload`), then one `MERGE INTO bronze.x USING (SELECT * FROM parquet.\`/Volumes/.../staging/{source}/{run_id}.parquet\`) ON keys ...` via `databricks-sql-connector`. Rationale: the connector's native params cap at ~255/statement (~25 rows); Parquet PUT + MERGE handles any batch, correct types, full idempotency, two API calls. Skip-unchanged: `WHEN MATCHED AND s.content_hash <> t.content_hash THEN UPDATE`. Single-row writes (state) use plain native-parameterized MERGE.

**Secrets/CLI/scheduling/fixtures**: `.env` + python-dotenv (`.env.example` committed; per-dev GitHub tokens). CLI `python -m scrapers.github --since 2026-06-19 --limit 500 [--fixtures] [--dry-run]` (typer). Local cron/APScheduler (GitHub 6h; arXiv daily; OpenAlex daily+weekly re-enrich; SHAB/Zefix daily 07:30 CET); ports unchanged to a GCP VM (systemd) or Databricks Jobs (wheel tasks + secret scopes). `--fixtures` replays checked-in deterministic JSON through the same normalize→validate→MERGE path (downstream teams get seed bronze day one; CI needs no secrets).

## GitHub scraper

Goal: top ~500 most-starred repos created in a rolling 30-day window; harvest core contributors; exclude already-funded teams downstream.
- **Discovery (REST Search)**: `GET /search/repositories?q=created:{start}..{end}+stars:>=10&sort=stars&order=desc&per_page=100`. 1000-cap workaround: top-N fast path (first 5 pages = top 500) + **created-date bisection** for completeness (split the window until each slice <1000; dedupe by `node_id`). REST (not GraphQL) for search: returns `total_count` cheaply, separate 30 req/min budget.
- **Hydration (GraphQL, 25 repos/query via aliases)**: metadata, topics, languages, licenseInfo, homepageUrl, `fundingLinks`, owner (`__typename`, org membership counts), + commit history `defaultBranchRef.target.history(first:100){oid additions deletions committedDate messageHeadline author{name email user{login}}}` (paginate to ~300 for young repos). README via REST `GET /repos/{o}/{r}/readme` (`Accept: raw`), truncate 200KB.
- **Contributors/profiles**: `GET /repos/{o}/{r}/contributors`. **Bot filter**: drop `type==Bot` or login `[bot]` or denylist (dependabot/renovate/github-actions/greenkeeper/snyk-bot/imgbot/allcontributors/codecov/pre-commit-ci/web-flow/weblate). **Core contributor**: rank by contributions; core iff `contributions >= max(3, ceil(0.05*repo_total))` AND rank ≤10; cap top 5/repo. Profiles via GraphQL 50 users/query (name, company, location, websiteUrl, twitter, email(public), followers, orgs, top repos, `socialAccounts` → self-declared LinkedIn/Twitter/Mastodon). Emails: public + commit `author.email` (discard `*@users.noreply.github.com`), stored with commit sha provenance.
- **Funded signals** (collect in bronze, classify in silver, exclude in gold): org `isVerified`/membersWithRole/custom domain; `fundingLinks`/FUNDING.yml; README regex `backed by|funded by|series [a-c]|pre-?seed|seed round|YC [SW]\d{2}|a16z|sequoia|accel|index ventures|lightspeed`; org email domain == homepage.
- **Rate-limit math** (single PAT; verified: REST 5,000/hr, Search 30/min, GraphQL 5,000 pts/hr, 304s free): initial backfill (500 repos + ~2k profiles) ≈ REST ~1,600–2,100/hr, GraphQL ~1,450 pts → **~25–35 min** wall-clock, >2× headroom. Daily incremental with ETag `If-None-Match` (304s free) → ~300–600 requests, <10 min.

## Papers scraper

- **arXiv spine** (verified: ≤2,000/call, 3-sec delay, single connection): `search_query=cat:cs.LG AND submittedDate:[... TO ...]&sortBy=submittedDate&max_results=200`, page `start+=200`, sleep 3s. Categories: cs.AI/LG/CL/CV/stat.ML (AI/ML), cs.RO/MA (robotics/agents), cs.DC/DB/SE (systems). Parse Atom with feedparser; dedupe cross-lists on arxiv id. Code-link regex over abstract+comment: `github.com/([\w.-]+)/([\w.-]+?)(?:\.git)?(?=[\s).,;\]'"]|$)` (+ gitlab, huggingface).
- **OpenAlex enrichment** (verified: free API key now required, `api_key=`, ~$1/day free ≈ 10k list calls; CC0): DOI batch lookup `filter=doi:A|B|...` (50/call); authorships with institutions (ROR, country), author id + ORCID, `cited_by_count`, `abstract_inverted_index`. Re-enrich weekly for citation velocity. **Semantic Scholar** optional (free key by request form, 1 RPS; `POST /graph/v1/paper/batch` 500 ids, `externalIds/citationCount/tldr`) — build so its absence is a no-op.
- **Papers-with-Code** (shut down 2025): one-time bronze load of the HF archive `pwc-archive/links-between-paper-and-code` (300,161 links, CC-BY-SA-4.0) → `bronze.paper_code_links`; forward coverage = our regex + README back-refs.
- **Unified `PublicationRecord`** (one schema for all scientific sub-sources; source-agnostic core + `source_extras` dict): `publication_uid`, `data_source` discriminator, `source_native_id`, `doi?`, `title`, `abstract?`, `published_at`, `venue?`, `categories[]`, `urls{landing,pdf?}`, `code_links[]`, `authors[{position, full_name, orcid?, source_author_id?, affiliation_strings[], is_corresponding?}]`, `citation_count?` + `_source` + `_as_of`, `retrieved_at`, `schema_version`.
- **Affiliation-inference limits** (state in schema comments + memos): affiliation is a submission snapshot; role invisible (student vs professor identical); ORCID coverage is a minority in CS; author↔person links are probabilistic → **candidate links with confidence**, confirmed by a second signal or the interview.

## Zefix scraper (Switzerland)

- **Official Zefix PublicREST** (recommended; free, credentials by email to `zefix@bj.admin.ch`): `GET /api/v1/sogc/bydate/{date}` (daily new registrations), `GET /api/v1/company/uid/{uid}` (CompanyFull: name, UID, legalForm, legalSeat, **purpose**, status, sogcPub[]; **no officers**), `GET /api/v1/legalForm` (resolve codes at runtime). Apify actor only as a paid stopgap (~$2/1k, also no officers). No-credentials fallback: opendata.swiss daily extract + SHAB.
- **Officers via SHAB/amtsblattportal** (verified live, public JSON, no auth): `GET https://amtsblattportal.ch/api/v1/publications?publicationStates=PUBLISHED&rubrics=HR&publicationDate.start=...&pageRequest.size=100` → list (id, publicationNumber HR01 new/HR02 mutation/HR03 deletion, cantons, title); detail `GET /api/v1/publications/{id}/xml` → full text incl. UID + "Eingetragene Personen" (name, function, signature rights, domicile). **LLM extraction** (Claude via Databricks) not regex — DE/FR/IT text, tiny volume (~40–80 HR01/day), emit `{full_name, function, signature_rights, domicile, confidence}`.
- **Pipeline/filtering**: daily SHAB HR01 → extract UID → Zefix company detail → LLM officer extraction + **purpose→startup-likeness** classification (`tech_startup_candidate|traditional|holding_shell|other`). Hard filters first: `legalForm ∈ {GmbH, AG}`, ACTIVE, exclude branches; cheap negative keywords (Immobilien/Treuhand/Holding/Gastro/Coiffeur) short-circuit before the LLM. **Capital-increase filings** feed the funding backbone (see [scoring-and-memo](scoring-and-memo.md)).
- Post-MVP analogues: UK Companies House (free API, officers included — best next target); German Handelsregister (via OpenCorporates/North Data); Austria Firmenbuch (paid).

## Hack Nation scraper (project showcase) — plug-and-play source

An **isolated script** (`sources/hacknation/`, not the shared `BaseScraper`) that writes to the same Databricks bronze and conforms to the PSR/venture contracts, so ER + scoring consume it with zero engine changes. See [WS-G](../workstreams/ws-g-hacknation-source.md) for the checklist. API mapped by Playwright 2026-07-18 (public JSON, login optional).

- **`GET https://projects.hack-nation.ai/.netlify/functions/bff-public-people-v2?limit=5000`** → `{data:{people:[…1000…], contributionsByUserId:{user_id:[{id,title}]}}}`. Person: `user_id, display_name, first/last_name, avatar_url, university, field_of_study, academic_degree, professional_situation, tagline, country, city`. Returned 200 unauthenticated → public. 317 users have contributions.
- **`GET .../bff-projects-public-v2?id={projectId}`** → full project: `title, summary, detail, category, techStack[], tags[], eventTitle, challengeTitle, winner, demoUrl, `**`githubUrl`**`, structured{usp,impact,problem,solution,implementation,targetAudience,jury_scope}, authorProfile{…,linkedinUrl,cvUrl}, team[{…,linkedinUrl,cvUrl,role}]`.
- **Flow**: people-v2 (1 req) → collect unique project ids → per-project detail (gentle rate limit + content_hash skip) → normalize.
- **Gotcha**: Netlify SPA-fallbacks unknown routes to `index.html` with HTTP 200 — always check `content-type: application/json` before parsing (only `bff-public-people-v2` and `bff-projects-public-v2` are real).
- **Value**: pre-assembled ventures (project + team + roles), the `githubUrl` ER spine (D8), founder education/location/LinkedIn, and a memo-grade structured pitch. Each project → a `hackathon_project` venture that auto-merges with the GitHub-repo venture on `githubUrl`.
- **Compliance**: participant-disclosed public data; LinkedIn URLs + CVs stored with provenance + erasure; CV fetch + content parsing enabled by default (owner decision 2026-07-19; `--no-cvs` opt-out, CVs fully inside the erasure cascade); gentle volume; login optional with own account. See [compliance.md](compliance.md).

## Compliance & etiquette

GitHub API within limits (no HTML scraping); arXiv ≤1 req/3s single connection; OpenAlex CC0 keyed tier; Zefix/SHAB statutory public registers (officer names are personal data → keep provenance + erasure). Descriptive User-Agent with contact email, backoff on 429, ETags, no login-walled pages. **LinkedIn scraping banned in the runbook.**
