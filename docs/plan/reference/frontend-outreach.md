# Frontend, proxy, outreach & interview

Lovable-hosted UI over Databricks via a serverless-secure proxy; consent-based outreach → AI interview → rescore. Owned by [WS-F](../workstreams/ws-f-frontend-and-outreach.md). Facts verified 2026-07-19.

## Secure Databricks access (no self-hosted backend)

**Lovable Cloud = Supabase-backed** (DB, auth with email/phone/Google/Apple, storage, edge functions, encrypted write-only secrets injected into function env; Resend from edge functions).

**Access pattern**: a single Supabase Edge Function router `dbx-proxy` holds `DATABRICKS_HOST` + service-principal `CLIENT_ID/SECRET` in Lovable Cloud secrets, mints **M2M OAuth** tokens (Databricks' recommended app auth; cached ~55 min), and executes **allowlisted, parameterized statements only** against a serverless SQL warehouse via `POST /api/2.0/sql/statements` (named `:params`, `wait_timeout` ≤50s, 25 MiB inline). Service-principal grants: SELECT on `gold.v_*`, INSERT/UPDATE on write tables, `CAN_USE` warehouse, `CAN_MANAGE_RUN` on the 3 jobs it may trigger.

**Why not direct browser→Databricks**: any shipped token is extractable (SPA bundle or XSS) and grants the *warehouse's* full scope — Unity Catalog can't distinguish app users, so one leaked credential = the whole pipeline incl. 5k people's personal data; no per-user authz, rate limiting, or audit. The proxy gives one server-held short-lived credential + per-endpoint authz on the Supabase JWT + an allowlist.

## Proxy API contract (`/v1/*`; VC routes require a Supabase JWT; interview routes use the outreach token)

| Endpoint | Method | Behavior |
|---|---|---|
| `/thesis` | GET/POST | list / upsert `gold.thesis` (MERGE) |
| `/thesis/:id/weights` | PUT | upsert weights; client re-ranks locally, no job |
| `/thesis/:id/ideal-candidate` | PUT | save JSON + Jobs API `run-now` (re-embed job) |
| `/ranking?thesis_id=` | GET | SELECT `gold.v_ranked_ventures` (precomputed) |
| `/venture/:id/memo` | GET | latest `gold.memo` |
| `/venture/:id/scores` | GET | per-category breakdown + evidence JSON |
| `/venture/:id/outreach` | POST | state transition + Resend send + token mint |
| `/venture/:id/rescore` | POST | Jobs API `run-now` (targeted rescore) |
| `/outreach?thesis_id=` | GET | status board rows |
| `/interview/:token` | GET | validate token → session bootstrap (consent, question plan) |
| `/interview/:token/message` | POST (SSE) | chat turn → Anthropic streaming; transcript rows to Supabase |
| `/interview/:token/complete` | POST | close, push transcript to Databricks, trigger extraction job |

**Data placement**: Databricks = source of truth (thesis/weights/ideal/scores/memos/outreach). Supabase Postgres holds only auth users + the latency-sensitive interview session/messages (streamed chat can't round-trip a warehouse), pushed to Databricks on completion. **Latency**: serve only precomputed gold views at request time (single-table SELECT <1s warm; ~200–800ms warehouse + ~50–150ms edge); cold start 5–10s → keep-alive `SELECT 1` during demo hours + skeleton UI. Long ops async via `run-now` + polling.

**Fallback**: if Lovable Cloud edge functions prove limiting (SSE, exec-time caps), move the internal tool to **Databricks Apps** (serverless Streamlit/React with workspace SSO + on-behalf-of UC access) — deletes the proxy layer but loses the Lovable UI and the public page; keep the interview page on Supabase either way (founders must not need workspace identities).

## Pages

1. Thesis form · 2. Ranked list (final score, confidence bar, status chips, funding badge, quality tier) · 3. Memo detail (per-category bars + evidence links + missing-data list; actions outreach/rescore/regenerate) · 4. Ideal-candidate editor (structured form) · 5. Weights editor (9 sliders, instant client-side re-rank) · 6. Outreach/interview kanban · public tokenized interview page · login (Supabase Auth).

## Outreach & AI interview

**State machine** (`gold.outreach`): `sourced → shortlisted → contacted → interview_started → interviewed → decided` (+ `bounced`, `expired`, `opted_out`, `declined`). Transitions only via the proxy; `history` append-only.

**Flow**: "Select for outreach" → row (`shortlisted`) → edge function `send-outreach`: mint token (128-bit random, store only SHA-256 hash, 14-day expiry) → render email → **Resend** → `contacted`. Email requirements: real sender identity + fund name + postal address; *why* contacted and **where the data came from** ("we came across your repository X / your paper Y" — GDPR Art. 14 transparency, link to a short privacy notice); one-click opt-out → suppression table checked before every send. CH/EU B2B posture: personalized 1:1, truthful sender info, working opt-out, low volume.

**Deliverability**: dedicated subdomain (`outreach.fundname.ch`) with SPF + DKIM (DNS is the long pole), DMARC `p=none`; plain personal email, reply-to a real mailbox; hackathon fallback = send from a partner's real mailbox and paste the link.

**Interview**: founder opens `/interview/{token}` → token validated (hash match, unexpired, not consumed) + bound to the first session (resume allowed; new sessions blocked; invalidated on completion) → consent screen (recorded verbatim) + optional structured asks (LinkedIn URL, CV upload to Supabase storage, funding history, traction metrics) → chat page driven by `claude-opus-4-8` (SSE; friendly, ≤15 min, covers the `venture_gaps` plan, probes numbers, never promises investment, "skip" allowed) → transcript in Supabase → on completion push to `silver` (extraction job writes an `interview` PSR + facts `source='interview', consent=true`) → targeted rescore + memo regen → status `interviewed` → VC decides (`decided`).

## Verified facts
- Databricks FMAPI hosts `databricks-claude-opus-4-8/-4-7/-4-6`, `-sonnet-5/-4-6`, `-haiku-4-5`, `-fable-5`; embeddings `databricks-gte-large-en` (1024-dim, 8192 tok).
- Databricks-hosted Claude does function-calling but **not** Anthropic's server-side web_search → web-search steps use the Anthropic API directly (`web_search_20260209`, $10/1k searches).
- Statement Execution API + OAuth M2M recommended over PAT. Lovable Cloud = Supabase (edge functions, secrets, Resend). Databricks Apps = the fallback host.
