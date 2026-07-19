# WS-F — Lovable app, proxy & interview loop

**Owner**: 1 dev · **Timing**: ~3.5 days · **Depends on**: WS0 fixtures + views (builds Day 1 against `dealflow_dev`); A6 for real scores.
**Goal**: the Lovable UI (ranking, memo, editors, outreach board), the secure `dbx-proxy`, and the outreach → AI-interview → rescore loop.

**Reference**: [frontend-outreach.md](../reference/frontend-outreach.md) · [interfaces § proxy contract](../reference/interfaces.md) · [compliance](../reference/compliance.md)

## Checklist

- [ ] **B1 — Lovable scaffold** (auth, routes, layout)
  - [ ] *Acceptance*: login gate works; unauthenticated redirect
- [ ] **B2 — `dbx-proxy` edge function** (M2M OAuth mint/cache, Statement Execution wrapper, endpoint allowlist)
  - [ ] *Acceptance*: `/v1/ranking` returns fixture rows; secrets absent from the bundle; no JWT → 401
- [ ] **B3 — Thesis form + weights editor + ideal-candidate editor**
  - [ ] *Acceptance*: saves persist to Databricks; the 9 sliders re-rank client-side <100 ms without network
- [ ] **B4 — Ranked list + memo detail** (score bars, evidence links, gaps, confidence + status + quality chips)
  - [ ] *Acceptance*: evidence links open sources; missing-data list renders
- [ ] **B5 — Outreach** (subdomain + SPF/DKIM in Resend, send function, opt-out + suppression, state transitions)
  - [ ] *Acceptance*: test email lands in inbox (not spam) with source disclosure + opt-out; state → contacted
- [ ] **B6 — Interview page** (token validation/binding/expiry, consent screen + uploads, streaming chat)
  - [ ] *Acceptance*: a founder without an account completes the interview from the emailed link; a second device is blocked; transcript stored
- [ ] **B7 — Completion sync + status board** (push transcript to Databricks; kanban over the state machine)
  - [ ] *Acceptance*: completion flips the board to `interviewed`; board shows all states
- [ ] **B8 — Polish** (cold-start skeletons, error states, demo seed script)
  - [ ] *Acceptance*: full demo path clickable end-to-end

## Notes & risks
- Develop against a fixtures-backed **mock of `/v1/*`** so frontend/backend proceed independently against the same JSON Schemas.
- Direct browser→Databricks is unacceptable (token leak = whole pipeline) — all reads go through the allowlisted proxy over `gold.v_*` views; long ops are async `run-now` + polling.
- Cold start 5–10s → warehouse keep-alive during demo hours + skeleton UI; pre-open the app before presenting.
- If Lovable Cloud edge functions fight us (SSE, exec caps), fall back to Databricks Apps for the internal tool; keep the interview page on Supabase.
