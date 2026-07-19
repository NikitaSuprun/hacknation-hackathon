# Venture Hunt — the WS-F frontend

The two-sided app for **Venture Hunt**: the investor instrument
(thesis → ranking → memo → choose → outreach board → admin) and the founder
surfaces (the tokenized interview, and the inbound `/chosen` intake).

Design system: [`docs/BRANDING.md`](../docs/BRANDING.md). Tokens live in
`src/index.css` + `tailwind.config.ts` — that code is the source of truth.

## Run it

```bash
npm install
npm run dev            # http://localhost:8080 — mock data, no backend needed
```

The **same bundle** runs on mock fixtures or on the real API; the choice is made
at boot by `src/lib/data/index.ts`:

| Precedence | Source | Notes |
|---|---|---|
| 1 | `?demo=1` or `?mode=mock\|live` | on-stage insurance: append `?mode=mock` if the warehouse dies mid-demo |
| 2 | `localStorage["chosen.mode"]` | remembers the last URL choice |
| 3 | `VITE_DATA_MODE` | `.env.demo` = mock; production build = live |
| 4 | default | mock |

### Live mode (against the in-repo API)

```bash
# terminal 1 — the Starlette app, zero credentials, fixture-backed
uv run python -m app serve --fixtures        # http://127.0.0.1:8799, password: demo

# terminal 2
npm run dev                                   # /v1 is proxied to :8799
# then open http://localhost:8080/?mode=live
```

Against the real warehouse: `uv run python -m app serve --catalog dealflow_dev`
with the Databricks `.env` plus `APP_PASSWORD` set.

The live layer is verified end-to-end by a guarded suite:

```bash
LIVE_URL=http://127.0.0.1:8799 npm run test -- live.integration
```

It skips silently without `LIVE_URL`, so `npm run test` stays offline.

## The demo

Fully client-side, zero network, presenter-driven.

```
/?demo=1                 clickable demo, engine armed
/?demo=1&autopilot=1     floating HUD; Space plays the 14-beat script
/?demo=1&beat=8          jump straight to a beat (panic recovery)
```

Controls: **Space** play/pause · **←/→** previous/next beat · beat dots to scrub ·
speed 1×/1.5×/2× · **Shift+R** full reset · **Ctrl+.** toggle the HUD. Touching
anything yourself auto-pauses the autopilot, so you can take over mid-script.

The story: sign in → thesis → ranked pool → GraspLab's memo and its cited gaps →
drag one weight and watch GraspLab take #1 → choose it → **the candidacy-sent
animation** → flip to Léna's side → consent → complete the candidacy → the AI
interview → back on the board, re-scored 75.1 → 79.9 with every new claim cited
to her own words.

State lives in memory (`src/mocks/state.ts`), so a hard refresh resets it —
use the `&beat=` deep link rather than reloading mid-presentation.

## Layout

```
src/
├─ lib/data/        DataSource — the one seam. Mock (fixtures + scripted chat)
│                   and Live (bearer auth, VARIANT parsing, turn-based chat
│                   wrapped as a token stream) are interchangeable.
├─ lib/domain/      contract types + zod mirrors of contracts/schemas/*.json
├─ lib/ranking/     the canonical re-rank — matches app/rescoring.py to 1 decimal
├─ lib/query.ts     client-side filters + semantic-ish prompt scoring
├─ mocks/           the demo database; fixtures/generated.ts is emitted by
│                   `npm run gen:fixtures` from ../fixtures/data/*.jsonl
├─ demo/            the 14 beats as data, plus the engine and HUD
├─ pages/           investor pages · interview/ · chosen/ · admin/
└─ components/      ui/ (shadcn on brand tokens) + scores/ memo/ outreach/
                    founder/ intake/ query/ admin/ celebration/
```

## Deploying

The demo is a static bundle — `npm run build:demo` produces `dist/`, which any
static host (Vercel, Netlify, Lovable) will serve as-is.

For the live app, serve the bundle from the Python app so it is same-origin and
needs no CORS: `scripts/sync-into-app.sh` builds and copies `dist/` into
`../app/static/`, backing up the existing SPA first. It is deliberately never
run automatically — coordinate before committing changes to `app/static/`.

## Known gaps

- `/chosen` submissions are stored in `localStorage`; the upstream app needs a
  `/v1/intake` endpoint before they reach the warehouse (flagged in `src/lib/intake.ts`).
- Live mode has no structured-asks or file-upload endpoints yet, so those steps
  are collected client-side only (upstream deferred them).
- `getVentureGaps` returns `[]` in live mode; the memo's `missing` bullets carry
  the gap list there.
