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

- [ ] **HN1 — Client → bronze**
  - [ ] `bff-public-people-v2` + per-project `bff-projects-public-v2`; unique project-id collection; content-type guard; gentle rate limit; optional authenticated session (own account)
  - [ ] Write `bronze.hacknation_people_raw`, `bronze.hacknation_projects_raw` (VARIANT payload + content_hash) via `merge_upsert`
  - [ ] *Acceptance*: 1000 people + all projects in bronze; re-run idempotent; runs without login
- [ ] **HN2 — Normalizer + ER rules**
  - [ ] `HacknationNormalizer` → PSR (source='hacknation') for author + each team member (name, university→org_norm, field_of_study/techStack→keywords, country/city, linkedin_url, cv_url, avatar_url)
  - [ ] ER **D7** (LinkedIn-URL equality → 0.97) + **D8** (project `githubUrl` → GitHub repo → contributors, name JW≥0.9 → 0.90)
  - [ ] *Acceptance*: a fixture HN person merges with their GitHub identity via githubUrl+name and via LinkedIn
- [ ] **HN3 — Venture builder extension**
  - [ ] `hackathon_project` anchor; author + `team[]` → `venture_member` (role_hint from `role`, author = founder guess); auto-merge with the repo venture on `githubUrl`
  - [ ] `structured` pitch → memo/scoring inputs; `university` → `institution_score`; `techStack` → keywords; `eventTitle`/`winner`/`jury_scope` → hackathon signal
  - [ ] *Acceptance*: a HN project becomes a scored venture with its given team; merges with the repo venture when that repo is scraped
- [ ] **HN4 — CV ingestion (gated)**
  - [ ] Store `cv_url`; optional fetch → UC Volume + LLM-extract education/experience **behind an off-by-default flag pending legal sign-off**; add `hacknation` + CV files to the erasure cascade + suppression
  - [ ] *Acceptance*: erasing a HN person removes the CV + all rows; CV content parsing is off by default
- [ ] **HN5 — Fixtures + plug-in proof**
  - [ ] HN fixture personas incl. one whose `githubUrl` matches a fixture repo
  - [ ] *Acceptance*: WS-G runs end-to-end on fixtures with **no edits** to WS-D/WS-E engine code (only the additive normalizer + rules + anchor enum)

## Why it's worth doing properly

Highest signal-density source for the demo: pre-assembled ventures (project + team + roles), the `githubUrl` ER spine, founder education/location/LinkedIn, and a full structured pitch (problem/solution/USP/impact) that is memo-grade — plus hackathon event/challenge/winner/jury data. It also serves as ground-truth for the venture/ER pipeline (the team is given).

## Risks
- CVs + LinkedIn are participant-disclosed but for platform display, not VC profiling → keep provenance + erasure; CV content parsing behind legal sign-off; gentle volume; respect platform ToS.
- Project-detail endpoint naming (`bff-projects-public-v2`, note word order) — content-type guard prevents SPA-fallback false positives.
