# WS-F — Lovable app, proxy & interview loop

**Owner**: 1 dev · **Timing**: ~3.5 days · **Depends on**: WS0 fixtures + views (builds Day 1 against `dealflow_dev`); A6 for real scores.
**Goal**: the Lovable UI (ranking, memo, editors, outreach board), the secure `dbx-proxy`, and the outreach → AI-interview → rescore loop.

**Reference**: [frontend-outreach.md](../reference/frontend-outreach.md) · [interfaces § proxy contract](../reference/interfaces.md) · [compliance](../reference/compliance.md)

## Checklist

- [ ] **B1 — Lovable scaffold** (auth, routes, layout) *(Lovable itself is SaaS-only; the in-repo equivalent ships as a vanilla-JS SPA in `app/static/` with hash routes + layout)*
  - [x] *Acceptance*: login gate works; unauthenticated redirect *(APP_PASSWORD session login in `app/auth.py`; the SPA redirects to `#/login` on 401; every `/v1/*` route 401s without a bearer session)*
- [x] **B2 — `dbx-proxy` edge function** (M2M OAuth mint/cache, Statement Execution wrapper, endpoint allowlist) *(in-repo as `app/api.py` + `app/store.py`: M2M OAuth via `tools.warehouse`, reads confined to the `app/queries.py` allowlist over `gold.v_*`, VARIANT columns travel as JSON strings; Supabase-hosted deployment remains SaaS-only)*
  - [x] *Acceptance*: `/v1/ranking` returns fixture rows; secrets absent from the bundle; no JWT → 401 *(fixtures mode serves the golden GraspLab row; the static bundle contains no credentials — the browser only ever holds the session token; unauthenticated → 401, covered in `tests/app/test_auth.py`)*
- [x] **B3 — Thesis form + weights editor + ideal-candidate editor**
  - [x] *Acceptance*: saves persist to Databricks; the 9 sliders re-rank client-side <100 ms without network *(PUT weights/ideal + POST thesis persist through the DataStore seam — fixtures overlay offline, `tools.db.DatabricksSink` MERGE live; sliders re-rank purely client-side in `app/static/app.js`, formula mirrored and tested via `app.rescoring.client_final_score`; ideal edits validate against the frozen `ideal` schema and re-embed)*
- [x] **B4 — Ranked list + memo detail** (score bars, evidence links, gaps, confidence + status + quality chips)
  - [x] *Acceptance*: evidence links open sources; missing-data list renders *(nine fixed memo sections; every cited bullet renders `source_url` anchors; missing bullets aggregate into the "Missing data → interview plan" card; asserted in `tests/app/test_memo.py`)*
- [ ] **B5 — Outreach** (subdomain + SPF/DKIM in Resend, send function, opt-out + suppression, state transitions) *(DNS/SPF/DKIM + deliverability are SaaS/DNS-console work — not reproducible in-repo)*
  - [ ] *Acceptance*: test email lands in inbox (not spam) with source disclosure + opt-out; state → contacted *(inbox delivery needs the verified Resend domain; everything else ships: `app/outreach.py` renders the compliance-complete email — sender identity, why contacted + data source, privacy note, one-click opt-out URL — checks ops.erasure_suppression + opted-out rows before every send, stores only sha256(token), and walks draft→sent with history; `ResendHttpMailer` posts to Resend when RESEND_API_KEY is set, `RecordingMailer` captures otherwise)*
- [x] **B6 — Interview page** (token validation/binding/expiry, consent screen + uploads, streaming chat) *(uploads deferred with the SaaS storage; chat is turn-based JSON rather than SSE streaming)*
  - [x] *Acceptance*: a founder without an account completes the interview from the emailed link; a second device is blocked; transcript stored *(token = sha256 match + 14-day expiry + first-session binding in `app/interview.py`; consent recorded verbatim as the first transcript entries; second session → 409; covered in `tests/app/test_interview.py`)*
- [x] **B7 — Completion sync + status board** (push transcript to Databricks; kanban over the state machine)
  - [x] *Acceptance*: completion flips the board to `interviewed`; board shows all states *(complete() writes gold.interview, flips the outreach to `interviewed`, and invokes `scoring.rescore.ingest_interview` (new score + memo rows, `rescore_score_id` backfilled); the board renders one column per DDL status)*
- [x] **B8 — Polish** (cold-start skeletons, error states, demo seed script) *(loading/error states in the SPA; the fixtures dataset is the demo seed — no separate script needed)*
  - [x] *Acceptance*: full demo path clickable end-to-end *(login → ranking → sliders → memo → outreach → interview link → consent → chat → complete → rescored ranking; exercised end-to-end by `tests/app/test_interview.py` and the `tests/app/test_cli.py` smoke)*

## Run notes

- **Fixtures demo (zero credentials)**: `uv run python -m app serve --fixtures` → open <http://127.0.0.1:8799> (password `demo`). Backed by `fixtures/data/*.jsonl` with an in-memory write overlay (golden files are never mutated), `RecordingMailer`, and the `ScriptedLLMClient`. The outreach response includes the interview link so the loop is demoable without an inbox.
- **Live mode**: `uv run python -m app serve --catalog dealflow_dev` needs the Databricks `.env` (`DATABRICKS_HOST/CLIENT_ID/CLIENT_SECRET/WAREHOUSE_ID`) plus `APP_PASSWORD`; optional `RESEND_API_KEY` switches mail from recording to real Resend sends, and `DATABRICKS_LLM_ENDPOINT` reroutes ai_query. Reads go through the `gold.v_*` views only; writes MERGE through `tools.db.DatabricksSink`.
- **Tests**: `uv run pytest tests/app` (offline; drives the whole loop in-process through starlette's TestClient).
- **Still SaaS-only for production**: Lovable scaffold, Supabase-hosted edge function + secrets, Resend subdomain + SPF/DKIM + deliverability testing, SSE streaming chat, founder uploads, and a multi-process session store (sessions/interview bindings are in-memory, single-process demo scope).

## Notes & risks
- Develop against a fixtures-backed **mock of `/v1/*`** so frontend/backend proceed independently against the same JSON Schemas.
- Direct browser→Databricks is unacceptable (token leak = whole pipeline) — all reads go through the allowlisted proxy over `gold.v_*` views; long ops are async `run-now` + polling.
- Cold start 5–10s → warehouse keep-alive during demo hours + skeleton UI; pre-open the app before presenting.
- If Lovable Cloud edge functions fight us (SSE, exec caps), fall back to Databricks Apps for the internal tool; keep the interview page on Supabase.
