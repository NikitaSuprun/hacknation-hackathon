# WS-G — Hack Nation source (plug-and-play)

**Owner**: 1 dev · **Timing**: ~2 days · **Depends on**: WS0 contracts + fixtures only. Builds fully independently and plugs in last with **zero changes** to the ER/scoring engines.
**Goal**: ingest the Hack Nation project showcase — a pre-assembled venture dataset (project = team + GitHub repo + structured pitch + founder backgrounds) — into the same Databricks storage, conforming to the bronze/PSR/venture contracts.

**Reference**: [scrapers.md § Hack Nation](../reference/scrapers.md) · [entity-resolution.md § D7/D8](../reference/entity-resolution.md) · [scoring-and-memo.md § hackathon ventures](../reference/scoring-and-memo.md) · [data-model.md](../reference/data-model.md) · [compliance.md](../reference/compliance.md)

## Verified API (Playwright, 2026-07-18; public JSON, login optional)

- `GET https://projects.hack-nation.ai/.netlify/functions/bff-public-people-v2?limit=5000` → `{data:{people:[…1000…], contributionsByUserId:{user_id:[{id,title}]}}}`. Person: `user_id, display_name, first_name, last_name, avatar_url, university, field_of_study, academic_degree, professional_situation, tagline, country, city`. 317 users have contributions. Returned 200 **unauthenticated** (data is public).
- `GET .../bff-projects-public-v2?id={projectId}` → `{data:{ id, title, code, summary, detail, heroImage, ownerId, createdAt, updatedAt, category, techStack[], tags[], eventId, eventTitle, challengeId, challengeTitle, companyId, companyName, winner, demoUrl, githubUrl, media[], structured{usp,impact,problem,solution,implementation,targetAudience,jury_scope}, programType, authorProfile{…,linkedinUrl,cvUrl}, team[{…,linkedinUrl,cvUrl,role}], review{…} }, meta}`.
- Netlify SPA-fallbacks unknown routes to `index.html` with 200 → **always check `content-type: application/json`** before parsing. Only `bff-public-people-v2` and `bff-projects-public-v2` are real for our needs.

## Design (isolated, contract-conformant)

Module `sources/hacknation/` — own deps (`httpx`; Playwright only if an authenticated session is ever needed), CLI `python -m sources.hacknation [--fixtures]`. **Not** built on the shared `BaseScraper` (deliberately separate), but writes bronze via the shared `tools/db.py merge_upsert` and emits `person_source_record` rows via a `HacknationNormalizer(SourceNormalizer)` — so ER + scoring consume it automatically. Flow: people-v2 (1 req) → collect unique project ids → per-project `bff-projects-public-v2?id=` (gentle rate limit + content_hash skip) → normalize.

## Checklist

- [x] **HN1 — Client → bronze**
  - [x] `bff-public-people-v2` + per-project `bff-projects-public-v2`; unique project-id collection; content-type guard; gentle rate limit (1 req/s token bucket); optional authenticated session not needed (endpoints answered unauthenticated)
  - [x] Write `bronze.hacknation_people_raw`, `bronze.hacknation_projects_raw` (VARIANT payload + content_hash) via the shared sink (`er.io.sink_all` → `tools/db` merge_upsert, registry keys)
  - [x] *Acceptance*: fixture replay lands 6 people + 2 projects in bronze with the provenance quad, skips the SPA-fallback route, and re-runs idempotently via content_hash MERGE (live 1000-people run pending Databricks credentials only — the endpoints are public)
- [x] **HN2 — Normalizer + ER rules**
  - [x] `HacknationNormalizer` (SourceNormalizer) + `er.normalize.hacknation_psrs` → PSR (source='hacknation') for people list + author + each team member (name, university→org_norm, field_of_study/techStack/tags→keywords, country/city→location, linkedin_url; cv_url flows to silver.person via survivorship — it is not a PSR column)
  - [x] ER **D7** (LinkedIn-URL equality, normalized both sides → 0.97, `det_linkedin`) + **D8** (project `githubUrl` → repo → core contributors, name JW≥0.90 → 0.90, `det_github_contrib`)
  - [x] *Acceptance*: fixture persona Lena merges with her GitHub identity via D8 (githubUrl+name JW 1.0); fixture persona Mira merges via D7 (LinkedIn spelled differently on each side)
- [x] **HN3 — Venture builder extension**
  - [x] `hackathon_project` anchor; author + `team[]` → `venture_member` (role_hint from `role`, author = founder guess, persons resolved through active ER links); auto-merge into the repo venture on normalized `githubUrl` (repo venture_id wins; only new persons append, so repo member rows stay byte-stable)
  - [x] `structured` pitch + `eventTitle`/`winner`/`jury_scope` + `techStack`/member universities flow into scoring extras via `scoring.ventures.hackathon_extras` (merged in the stage-A context)
  - [x] *Acceptance*: the fixture GraspFM demo project (githubUrl == grasp-anything) merges into the GraspLab repo venture with an unchanged member set; VoiceLab becomes its own hackathon_project venture with its given team (author = founder guess) and a golden score row
- [x] **HN4 — CV ingestion (gated)**
  - [x] `cv_url` stored as pointer only on silver.person; fetch/parse behind the off-by-default `HACKNATION_CV_INGESTION` env flag (`sources/hacknation/cv.py` returns a typed disabled/pending_signoff result and never fetches today); `hacknation` added to the erasure cascade (bronze delete + suppression hash) and the CV pointer purge is recorded in the erasure log notes for the UC Volume runbook
  - [x] *Acceptance*: erasing a HN person plans the bronze.hacknation_people_raw delete, the suppression entry, and the CV purge note; stage-0 re-runs resurrect nothing; CV content parsing is off by default
- [x] **HN5 — Fixtures + plug-in proof**
  - [x] HN fixture personas: Lena's HN identity on the project whose `githubUrl` matches the fixture grasp-anything repo (D8), Mira with a GitHub `socialAccounts` LinkedIn twin (D7), HN-only Noah on the HN-only VoiceLab project
  - [x] *Acceptance*: the full ER pipeline and the venture builder run end-to-end offline over fixtures including Hack Nation with **no edits** to the WS-D/WS-E engines beyond the additive extractor registration, rules, and anchor handling; the pre-existing fixture rows stayed byte-identical

## Run notes (2026-07-19)

- CLI: `uv run poe hacknation -- --fixtures --dry-run` (or `python -m sources.hacknation [--fixtures] [--dry-run] [--limit N] [--catalog dealflow_dev]`). `--fixtures --dry-run` is the credential-free path: wire-shaped fixtures under `sources/hacknation/fixtures/` replay through httpx.MockTransport at the transport layer, and the NullSink records the bronze rows. `--limit` caps the per-project detail fetches.
- The committed replay set deliberately includes a project id (`hnp-spa-01`) that answers the Netlify SPA index page with HTTP 200; the content-type guard skips it with a warning (`skipped_non_json=1`), proving the guard on every run.
- CV ingestion is OFF by default: leave `HACKNATION_CV_INGESTION` unset. Even when set, the fetch is a typed no-op pending legal sign-off.
- A live run needs only Databricks credentials (`.env` per the WS0 runbook) — the two Hack Nation endpoints are public JSON, no login. Suppression for `bronze.hacknation_people_raw` is already enforced by `tools/db.SUPPRESSION_RULES`.
- Deviation from the plan text: the bronze-tables extractor `hacknation_psrs` lives in `er/normalize.py` alongside the other stage-0 extractors (so er never imports sources), and `sources/hacknation/normalize.HacknationNormalizer` adapts it onto the SourceNormalizer protocol.

## Why it's worth doing properly

Highest signal-density source for the demo: pre-assembled ventures (project + team + roles), the `githubUrl` ER spine, founder education/location/LinkedIn, and a full structured pitch (problem/solution/USP/impact) that is memo-grade — plus hackathon event/challenge/winner/jury data. It also serves as ground-truth for the venture/ER pipeline (the team is given).

## Risks
- CVs + LinkedIn are participant-disclosed but for platform display, not VC profiling → keep provenance + erasure; CV content parsing behind legal sign-off; gentle volume; respect platform ToS.
- Project-detail endpoint naming (`bff-projects-public-v2`, note word order) — content-type guard prevents SPA-fallback false positives.
