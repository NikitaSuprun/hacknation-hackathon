# Roadmap, milestones & checklists

Stages, integration milestones, the Day-0 external checklist, and the end-to-end verification script. Check items off as we build.

---

## Stage 0 — Foundations (Day 0–1, blocks everyone)

- [ ] Day-0 external checklist complete (below)
- [ ] [WS0](workstreams/ws0-platform-and-contracts.md) through **contract freeze**
- [ ] **Exit criterion**: every team can query fixture data in `dealflow_dev` and `pre-commit run --all-files` is green on the skeleton

## Stage 1 — Parallel build against fixtures (Days 1–4)

- [ ] [WS-A GitHub scraper](workstreams/ws-a-github-scraper.md) passes its acceptance criteria on fixtures
- [ ] [WS-B Papers scraper](workstreams/ws-b-papers-scraper.md) …
- [ ] [WS-C Zefix scraper](workstreams/ws-c-zefix-scraper.md) …
- [ ] [WS-D Entity resolution](workstreams/ws-d-entity-resolution.md) …
- [ ] [WS-E Scoring & memo](workstreams/ws-e-scoring-and-memo.md) …
- [ ] [WS-F Lovable app + proxy + interview](workstreams/ws-f-frontend-and-outreach.md) …
- [x] [WS-G Hack Nation source](workstreams/ws-g-hacknation-source.md) — plug-and-play; builds independently, plugs in last (code + fixtures done; live warehouse staged)
- [ ] **Exit criterion**: fixture E2E runs (thesis → pool → scores → memo → UI → interview) with zero real implementations

## Stage 2 — Live integration (Days 4–5)

- [ ] Scrapers backfill 30 days into `dealflow` bronze
- [ ] Entity resolution on real data; spot-check the review queue
- [ ] Stage A scores on all candidates; Stage B + memos on top-25
- [ ] UI pointed at `dealflow`; dry-run outreach to a teammate address
- [ ] Full loop rehearsal (outreach → interview → rescore → memo regen)
- [ ] **Exit criterion**: the live E2E demo script (below) passes

## Stage 3 — Post-MVP roadmap (documented, not built)

- [ ] Scheduled Databricks Jobs (or GCP VM) for continuous scraping
- [ ] Licensed enrichment (People Data Labs / Coresignal) if coverage demands
- [ ] UK Companies House as the next company register
- [ ] Monitoring/alerting; Databricks Apps fallback if Lovable limits bite
- [ ] Legal review before real founder outreach at volume
- [ ] Migrate off Databricks Free Edition to a commercial workspace

---

## Day-0 external checklist (external latency — start first)

- [ ] Databricks **Free Edition** workspace (no card; non-commercial) → catalogs, serverless SQL warehouse, service principal
- [ ] **Model smoke test**: `ai_query('databricks-gte-large-en','hi')` returns 1024 floats; list resolvable `databricks-claude-*` endpoints; record the Anthropic-API fallback decision
- [ ] **Email `zefix@bj.admin.ch`** for free PublicREST credentials (unknown turnaround; SHAB + opendata.swiss need none)
- [ ] **OpenAlex API key** (self-serve, free) · **Semantic Scholar key** (request form, optional) · **GitHub PAT per developer** · **Anthropic API key** (web-search budget)
- [ ] **Lovable project + Lovable Cloud** enabled; Supabase secrets for the service principal
- [ ] **Resend** account + outreach subdomain **SPF/DKIM DNS** records (propagation is the long pole)
- [x] Repo scaffold + full pre-commit gate green on skeleton (see [engineering-standards](reference/engineering-standards.md))
- [ ] Optional demo boosters (terms verified): People Data Labs free tier (100 lookups/mo, no card), Coresignal trial, Serper.dev key (2,500 free queries). Do **not** sign up for Enrichlayer/Lix (LinkedIn-scraping lineage).

---

## Live E2E demo script (Stage 2 exit)

- [ ] 1. Save a fresh thesis in the UI → candidate pool materializes
- [ ] 2. Ranked list shows real scraped ventures with score + confidence + status chips
- [ ] 3. Open a memo → every bullet is cited (`source_url`) or explicitly marked missing
- [ ] 4. Edit the ideal candidate → the similarity/match column reorders
- [ ] 5. Drag a weight slider → instant client-side re-rank (no network round-trip)
- [ ] 6. Select a venture → outreach email lands in a test inbox with source disclosure + opt-out
- [ ] 7. Complete the interview from the emailed link on a phone; second device is blocked
- [ ] 8. Score + memo visibly update after the interview
- [ ] 9. `erase_person` on a test identity → gone everywhere; a re-scrape does not resurrect it
- [ ] 10. `ops.llm_run_log` total spend < budget

---

## Cost budget (verified pricing)

- Scraping APIs: **$0** (GitHub / arXiv / OpenAlex free tier / SHAB / Zefix)
- Institution/funding data: **$0** (Leiden CC0, ROR, Accel PDF figures, Crunchbase-2013 CC-BY, Wikidata, Startupticker, Zefix/SOGC); optional Crunchbase Pro ~$99/mo
- Stage A full refresh: ~$30–40 (Batch API −50% option)
- Stage B (top-25/thesis): ~$15–25 · memos ~$8 · interview+extraction ~$1/interview
- Career enrichment (top-K only): ~$0.045–0.09/candidate → $2–5 per 20–50-person shortlist
- **Total demo < $150** — Databricks Free Edition is $0 within fair-use quotas, so the Anthropic API is essentially the only spend.
