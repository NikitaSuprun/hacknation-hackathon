# Handover — read this first

Context dump so any teammate (or a fresh Claude session) is oriented without re-deriving anything. Pairs with [README.md](README.md) (index) and the `reference/` + `workstreams/` docs. All volatile facts were web-verified on 2026-07-19 unless noted; the Hack Nation API was mapped by Playwright on 2026-07-18.

## The product in one paragraph

A VC fund inputs a thesis (sectors, geography, check size, stage) and an editable "ideal candidate". The system scrapes early builder signals — GitHub trending-new repos, recent papers (arXiv + OpenAlex), new Swiss incorporations (Zefix/SHAB), and the Hack Nation hackathon showcase — links every signal to golden person records with confidence-scored entity resolution, groups people+artifacts into ventures, scores each venture on 8 rubric categories + an ordinal-aware ideal-candidate match + a confidence score, ranks them in a Lovable UI backed by Databricks, generates cited investment memos, and runs consent-based AI interviews with finalists that fill data gaps and trigger rescoring.

## Confirmed decisions (+ why)

1. **Scope** = hackathon MVP (end-to-end demo in days; production paths documented, not built).
2. **Platform** = Databricks **Free Edition** (non-commercial, no card; migrate to a commercial workspace before commercial use). Constraints: 1 SQL warehouse @2X-Small, 5 concurrent job tasks, "certain models not available", fair-use daily shutoff → mitigated by a Day-0 model smoke test + Anthropic-API/local-Splink fallbacks.
3. **Frontend** = Lovable + Lovable Cloud (Supabase). No self-hosted backend; Databricks reached only through a Supabase Edge Function proxy holding a service-principal M2M OAuth credential (never a browser-held token).
4. **IDs** = deterministic **UUIDv5** for source-keyed entities, random **UUIDv4** for golden persons. Rationale: Spark has no unsigned int; UUIDv5 makes MERGE idempotent + fixture FKs stable across machines.
5. **Identity model** = facts attach to `person_source_record` (per-source identity); golden `person` = a reversible set of `person_source_link` rows. ER mistakes are fixed by link surgery, never by touching facts. Connections are an **edge table** (`person_connection`), not an array on `person` (arrays can't carry per-edge weight/evidence and go stale on merge).
6. **Entity resolution** = deterministic rules (D1–D8) + **Splink 4 on DuckDB locally** + LLM adjudication of the 0.60–0.90 band + human review of 0.45–0.60. Auto-merge floor 0.90, never on name alone; merges reversible.
7. **Scoring** = hybrid over a **shared calibrated feature layer**: 8 evidence-cited 0–100 rubric categories + a **structured** ideal-candidate match, all VC-weighted. Embeddings do **domain-fit only**; ordinal prestige (MIT>KTH) and magnitudes live in the `institution_score` table + normalized numeric features — a raw profile embedding cannot rank MIT>KTH or weigh 8,200 stars ≫ 82.
8. **Institution scoring** = our own `institution_score` table (universities + companies → 0–100), seeded from license-clean sources; ship only CC0/CC-BY/public-register data, hand-curate the rest.
9. **Funding backbone** = free path (Zefix/SOGC capital-increase filings as a realtime CH "raised a round" proxy + Startupticker + Crunchbase-2013 CC-BY + Wikidata); powers the funded-founder score and the "exclude already-funded" filter.
10. **Career data** = store LinkedIn/portfolio URLs (public-sourced) + web-search enrichment agent + provider free tiers + personal-site enrichment + consent intake; optional LinkedIn self-scraper isolated behind the `EnrichmentProvider` interface (ToS-flagged).
11. **Age/gender** = stored per spec but **excluded from all scoring**; photo-based inference behind an **off-by-default flag pending legal sign-off**.
12. **Hack Nation** = first-class plug-and-play source; each project is a `hackathon_project` venture auto-merging with the GitHub-repo venture on `githubUrl`; **CVs fetched AND parsed by default** — owner decision **2026-07-19**, superseding the earlier "parsing behind the legal-sign-off flag"; opt-out `--no-cvs`, CVs fully inside the erasure cascade (suppression on `bronze.hacknation_cvs_raw` + deterministic volume-file delete).
13. **Quality over quantity** = venture-likeness gate, ≥2-source corroboration, conflict flagging, a quality gate into the scored pool, and a per-cycle quality report (golden-set ER precision target ≥95%).
14. **Interfaces** = every seam is a typed, versioned contract implemented by fixtures on Day 1; the whole pipeline runs on fixtures before any real code. The 8+1 `CategoryScorer`s, `EnrichmentProvider`s, `FundedFounderResolver`s are the finest-grained parallel units.
15. **Engineering standards** = `uv`/`poe`, strict pre-commit gate (ruff, basedpyright+ty strict, pydoclint, custom hooks), parametrized generics, minimal why-only comments, no-AI-watermark commits, Mermaid-only diagrams, `pip-licenses` → `THIRD_PARTY_LICENSES`, `LicenseRef-Proprietary`.

## Verified facts (with sources)

| Fact | Value | Source |
|---|---|---|
| Databricks Free Edition | serverless-only, 1 warehouse @2X-Small, 5 concurrent job tasks, non-commercial, fair-use shutoff, "certain models not available" | learn.microsoft.com/azure/databricks/getting-started/free-edition-limitations |
| Databricks FMAPI models | `databricks-claude-opus-4-8/-4-7/-4-6`, `-sonnet-5/-4-6`, `-haiku-4-5`, `-fable-5`; embeddings `databricks-gte-large-en` (1024-dim, 8192-tok) | docs.databricks.com/…/foundation-model-apis/supported-models |
| Databricks Claude ≠ web_search | function-calling yes; Anthropic server-side web_search NO → web-search steps use the Anthropic API directly (`web_search_20260209`, $10/1k) | docs.databricks.com/…/query-anthropic-messages; platform.claude.com/docs/…/pricing |
| Statement Execution API + OAuth M2M | `POST /api/2.0/sql/statements`, named `:params`, ≤50s, 25 MiB; M2M service principal recommended over PAT | docs.databricks.com/…/sql-execution-tutorial; …/auth/oauth-m2m |
| GitHub limits | REST 5,000/hr, Search 30/min (1,000 results/query), GraphQL 5,000 pts/hr, 304s free | docs.github.com rate-limit pages |
| arXiv API | ≤2,000/call, 3-sec delay, single connection; `submittedDate:[…]`, `cat:` | info.arxiv.org/help/api |
| OpenAlex 2026 | polite pool retired; free API key required; ~$1/day free ≈ 10k list calls; CC0 | developers.openalex.org |
| Papers-with-Code | shut down 2025; archive `pwc-archive/links-between-paper-and-code` (300,161 links, CC-BY-SA-4.0) on HF | huggingface.co/datasets/pwc-archive/… |
| Zefix | free PublicREST (creds by email to zefix@bj.admin.ch); `sogc/bydate/{date}`, `company/uid/{uid}`; **no officers** in the API | zefix.admin.ch/ZefixPublicREST |
| SHAB officers | amtsblattportal.ch `/api/v1/publications?rubrics=HR` public JSON, no auth; publication text has "Eingetragene Personen" | live probe + amtsblattportal.ch |
| Splink | v4.0.16 (2026-03), MIT, DuckDB/Spark; ~1M rec/min on a laptop | pypi.org/project/splink |
| Lovable Cloud | Supabase-backed (auth, edge functions, encrypted secrets, storage); Resend from edge functions | docs.lovable.dev/features/cloud; supabase.com/docs/guides/functions |
| Enrichment (search-agent) | ~$0.045–0.09/candidate (Haiku + web_search / Serper); Google CSE closed to new users, Brave free tier removed Feb 2026; PDL free 100/mo | platform.claude.com/docs/…/pricing; serper.dev; peopledatalabs.com/pricing |
| University prestige (shippable) | **Leiden Ranking Open Edition (CC0)** only; QS/THE/ARWU/US News = no commercial license; CSRankings = CC BY-NC-ND | open.leidenranking.com/resources |
| University outcome | PitchBook free founder-ranking articles; Dealroom European Spinouts; 2026 Deep-Tech Report (ETH #1, EPFL #2 for deep-tech founders) | pitchbook.com/news/articles; deeptechnation.ch |
| Company founder-factory | free Accel×Dealroom "Founder Factories" PDF (Klarna 66, Spotify 61…); SignalFire "Unicorn DNA" (US per-capita) | accel.com/founder-factory; signalfire.com/blog |
| Funding backbone | Crunchbase 2013 CC-BY snapshot + Wikidata (P112/P69/P2088) + Startupticker SVCR + Zefix/SOGC capital-increase | github.com/notpeter/crunchbase-data; startupticker.ch |
| Hack Nation API | `bff-public-people-v2?limit=5000` (1000 people, public 200), `bff-projects-public-v2?id=` (githubUrl, team[]+roles, linkedinUrl, cvUrl, structured pitch, event/challenge/winner/jury) | Playwright probe 2026-07-18 |

## Open items / watch-outs

- **Legal sign-off** still required before enabling photo-based age/gender inference (off by default, excluded from scoring). CV content parsing no longer waits on it — default-on per the 2026-07-19 owner decision (decision 12).
- **Zefix credentials**: email zefix@bj.admin.ch Day 0 (unknown turnaround); SHAB + opendata.swiss work meanwhile.
- **Outreach deliverability**: outreach subdomain SPF/DKIM DNS Day 0 (propagation is the long pole).
- **`deep-research` skill anomaly**: during planning a subagent's `Skill("deep-research")` call returned a malformed, prompt-injection-looking payload (fake "plan mode" + a nonexistent tool). It was disregarded; worth checking why that skill returned that content before relying on it.
- **Free Edition ceilings**: keep jobs modest; run heavy backfills off-peak; migrate to a paid workspace for scale/commercial use.

## Build state (2026-07-19)

- **WS-G done in code + fixtures; warehouse steps staged behind `.env` creds.** Package `sources/hacknation/` (httpx client → bronze, `HacknationNormalizer`, silver.project writer, D7/D8 rule SQL, CV pipeline, CLI `python -m sources.hacknation` with `--fixtures/--dry-run/--limit/--no-cvs`); additive PSR columns `avatar_url`/`cv_url`; new `bronze.hacknation_cvs_raw`; `match_method` additions `det_linkedin`/`det_hn_repo`; fixture personas incl. one whose `githubUrl` matches the fixture repo `grasplab/grasp-anything`.

## Doc map

- Start: [README.md](README.md) · [roadmap.md](roadmap.md) (Day-0 checklist + E2E script)
- Build: `workstreams/ws0` (do first) → `ws-a`…`ws-g` (parallel checklists)
- Design detail: `reference/` — data-model, entity-resolution, scoring-and-memo, scrapers, frontend-outreach, interfaces, engineering-standards, compliance

## Conventions (enforced)

No AI watermark in commits; Mermaid-only diagrams; docs read human-written (draft prose with `codex` given background, then edit); strict pre-commit gate (see [engineering-standards](reference/engineering-standards.md)); additive-only schema changes after the Day-1 contract freeze.
