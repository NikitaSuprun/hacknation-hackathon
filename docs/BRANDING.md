# CHOSEN, brand & design system

**Product:** Maschmeyer's Chosen Portfolio · **Wordmark:** CHOSEN · **Tagline:** *You don't apply. You get chosen.*
**Canonical tokens:** `frontend/src/index.css` (CSS custom properties) + `frontend/tailwind.config.ts` (utility mapping). This document explains them; the code is the source of truth.

---

## 1. The brand idea

CHOSEN inverts the application. Investors hunt; founders are found. Every design choice encodes that inversion:

- **Paper & ink** carry the *work of judging*, the investor side is a working document: memos, scores, hairline rules, mono-set numbers on warm cream.
- **The electric blue is the act of choosing**, it appears only when a decision is being made or has just been made. This single rule answers nearly every "should this be blue?" question with *no*.
- **Two registers, one system.** The investor side is an *instrument*: dense, precise, data-first. The founder side is a *letter*: warm, personal, single-purpose. Same palette, same type, the founder side simply gets softer corners (8px), a larger body size, and the paint-swirl moment.

The emotional core: **being chosen is an honor.** Nothing on the founder side may ever feel like a form.

## 2. Voice & tone

**Investor side**, precise, confident, data-first. Verbs name the action. Numbers are always mono. No exclamation marks, no marketing adjectives.

> Button: **"Send outreach"** (never "Submit", never "Reach out!")
> Empty list: *"No ventures ranked yet. Run sourcing or widen your thesis filters."*
> Caveat: *"Traction capped at 70 until confirmed in interview."*
> Cold start: *"Warming the warehouse, first load takes a few seconds."*

**Founder side**, warm, respectful, zero-beg.
**Banned words:** apply, application, submit, form, sign up, candidate pool.
**Required vocabulary:** chosen, candidacy, invitation, your story, your work.

> Hero: **"You've been chosen."**
> Sub: *"{Fund} reviewed your public work, nothing here is an application. You were already selected."*
> Consent CTA: **"I agree, continue"** · Decline: **"Not interested"** (one click, no guilt copy)
> Interview: *"About 15 minutes, conversational. Skip anything."*
> Inbound intake (/chosen): **"Put yourself on the radar."**, *"We don't read applications. We read your work. Tell us where it lives."*
> Transparency (GDPR Art. 14, make compliance part of the brand): *"Why you: we found your repository X. What we hold: public activity only, until you choose to share more."*

## 3. Palette

| Token | Value | Role |
|---|---|---|
| `--paper` | `#FAF7EA` | The canvas. Warm cream, never pure white. |
| `--ink` | `#0E0E0C` | Text, bars, structure, never pure black. |
| `--quiet` | `#6F6F63` | Metadata, secondary text. Never lighter than this. |
| `--line` | `rgba(14,14,12,.12)` | Hairline rules (decorative, contrast-exempt). |
| `--line-strong` | `rgba(14,14,12,.24)` | Chip borders, control outlines. |
| `--wash` | `rgba(14,14,12,.05)` | Hover rows, skeleton base, founder chat bubbles. |
| `--electric` | `#0037FF` | **The decision.** CTA, active state, score highlight, chosen moment. |
| `--electric-hover` | `#002BD1` | Hover on electric (darker = contrast improves). |
| `--electric-on-ink` | `#4D6FFF` | The *only* accent allowed on ink surfaces. |
| `--electric-wash` | `rgba(0,55,255,.08)` | Selection tint, interview-cited highlights. |
| `--danger` | `#A8200D` | Errors and negative outreach states only. No green anywhere, positive outcomes are expressed with electric or ink. |

**Contrast (WCAG 2.1, computed):**

| Pair | Ratio | Verdict → rule |
|---|---|---|
| ink on paper | **18.0:1** | AAA, default text |
| electric on paper | **6.5:1** | AA (AAA large), links/CTAs at any size ≥12px |
| paper on electric | **6.5:1** | AA, button labels |
| electric on ink | **2.75:1** | **FAIL, never do this.** Use `--electric-on-ink` (4.6:1). |
| quiet on paper | **4.7:1** | AA (barely), metadata only, never lighten |

**The accent budget:** at most **one electric element per viewport region**, the primary CTA, *or* the active state, *or* the score highlight. Never decoration, never large fills except the CTA and the swirl.

## 4. Typography

All self-hosted woff2 in `frontend/public/fonts/`, zero external requests.

| Face | Source | Role |
|---|---|---|
| **Clash Display** (400/500/600) | Fontshare, free | Wordmark, display, h1-h2 only |
| **DM Sans** (variable 400-700) | Google Fonts, free | Body, UI, forms |
| **Geist Mono** (variable 400-600) | Vercel, free | Every number, rank, score, timestamp, label |

Scale (Tailwind `text-*` tokens):

| Token | Size / line | Face & weight | Tracking |
|---|---|---|---|
| `display-xl` | clamp(56-120px) / 0.95 | Clash 500 | −0.02em |
| `display` | 64 / 68 | Clash 500 | −0.02em |
| `h1` | 40 / 44 | Clash 500 | −0.01em |
| `h2` | 28 / 34 | Clash 500 | −0.01em |
| `h3` | 20 / 28 | DM Sans 600 | 0 |
| `h4` | 17 / 24 | DM Sans 600 | 0 |
| `body` | 16 / 26 | DM Sans 400 | 0 |
| `small` | 14 / 20 | DM Sans 400 | 0 |
| `mono-data` | 13 / 20 | Geist Mono 400, tabular | 0 |
| `mono-label` | 12 / 16 | Geist Mono 400, UPPERCASE | +0.06em |

`.mono-label` (uppercase mono eyebrow) is the system's Swiss signature, section eyebrows, column headers, status chips, captions. Reading measures: `max-w-measure` (62ch, memo prose), `max-w-measure-narrow` (34ch, ledes and empty states).

## 5. Grid, spacing, radius, elevation

- **Macro grid:** `--maxw 1176px` (84 × 14px cells), gutters `28px` / `56px`, section rhythm `112px`. Micro-spacing stays on Tailwind's 4px steps.
- **Hairlines over boxes:** structure comes from 1px `--line` rules, not from shaded containers. No gray panel backgrounds, only paper, wash and ink.
- **Radius:** `0` cards/tables/rows (Swiss squareness) · `4px` controls · `8px` (`rounded-warm`) founder-side surfaces only · pill for chips.
- **One shadow** (`--shadow-lift`), used only for lifted/dragged/overlay states.

## 6. Iconography

Lucide, 16/20px, stroke 1.5, `currentColor`, outline only. Never icon-only actions (except close). Meaning is never carried by an icon alone, a mono label always accompanies it.

## 7. Motion

Durations: **120ms** micro (hover/press) · **180ms** standard (fades, chips) · **240ms** emphasis (reorders, flips) · **320ms** large moves · **1600ms** signature ceiling.
Easings: `--ease-swift cubic-bezier(0.22,1,0.36,1)` default · `--ease-travel cubic-bezier(0.65,0,0.35,1)` movement · `--ease-spring cubic-bezier(0.34,1.56,0.64,1)` chip flips only.

Rules (the "snappy" contract):
1. Animate **transform and opacity only**, never width/height/box-shadow/layout.
2. The only infinite loops are the skeleton shimmer and the (rare) ambient swirl, which pauses when hidden.
3. No scroll-linked animation. **No custom cursor. No always-on WebGL.**
4. `prefers-reduced-motion` collapses everything to ≤150ms crossfades (global clamp in `index.css`).
5. Skeletons mirror the final layout exactly; after ~3s of cold start, add *"Warming the warehouse…"*.

## 8. The signature moment, "candidacy sent"

The one place the brand celebrates. Fired through `lib/celebration.ts` (`celebrate({ventureId, ventureName, founderName, origin})`), the real send action and the demo engine share the same code path. Implemented in `components/celebration/CandidacySentOverlay.tsx` (CSS only):

| t | Beat |
|---|---|
| 0-120ms | Circular clip-path reveal expands from the confirm button's coordinates, beneath it, three pre-blurred conic/radial paint layers (electric / cream / low-ink) turning slowly on transform |
| 300-900ms | Center card rises: `CANDIDACY SENT` mono-label in electric · "{Venture}, chosen." in Clash h2 |
| 1100-1600ms | Fade out; scroll restored |

Skippable on any pointer/key event. Reduced motion: 150ms card crossfade, no burst. **The founder-side mirror** is the `/interview/{token}` hero: paint-poster background behind a ~70% cream veil, "You've been chosen." rising per-word, interactive in ≤1.4s.

The paint-swirl aesthetic (Balatro-inspired) appears **only** at ceremony surfaces: landing hero, founder hero, the sent overlay. Never inside the working instrument.

## 9. Wordmark & favicon

- **CHOSEN** in Clash Display. Display sizes: weight 500, −0.02em, uppercase. Nav size (14-16px): weight 600, +0.08em tracking.
- Full name *"Maschmeyer's Chosen Portfolio"* is always a mono-label eyebrow or footer line, never set in Clash next to the wordmark.
- Favicon: electric square, cream "C" (`frontend/public/favicon.svg`). Also the avatar for outreach email.

## 10. Component vocabulary (quick reference)

- **Ranked row** (56px, hairline-separated): mono rank · name + quiet descriptor · badges/chips · right: score (mono) over a 4px ink bar with a 2px confidence bar beneath. Accent only on selection and rank-change flashes. `needs_more_data` rows: dashed chip, 60% bars, disabled choose.
- **Status chips:** outlined pills, mono 11px uppercase, 6px state dot, electric = live pipeline, quiet = early, ink = decided, danger = bounced/declined/opted_out/expired.
- **Memo:** 9 fixed sections; every bullet cited or explicitly *missing* (dashed rule + "missing, asked in interview"); evidence opens an in-app citation card (fictional demo URLs never navigate); interview-cited facts get an electric-wash highlight + "consented" tag.
- **Weight sliders:** 2px hairline track, square ink thumb (electric while dragging), instant client-side re-rank (<100ms, zero network).
- **Kanban:** continuous paper, vertical hairlines, no gray wells; cards square; negative states collapsed and muted.
- **Chat:** interviewer = flush-left text with a 2px ink rule (a letter, not a bubble); founder = wash bubbles, `rounded-warm`; monochrome except the send button.
- **Founder cards:** max-w 560-640px, `rounded-warm`, body 17px.

## 11. Do / Don't

**Do:** paper everywhere · hairlines over shadows · mono for every number · accent = decision · skeletons that mirror layout · name failures in error states.
**Don't:** pure `#FFF`/`#000` · gray panel backgrounds · electric on ink (use `--electric-on-ink`) · accent hovers on non-primary elements · animate layout properties · more than one swirl per page · "apply/submit" anywhere a founder can read · emoji in UI · WebGL inside the investor instrument · em or en dashes in any copy (write with periods, commas, colons, middots).

---

*References that shaped this system: tile.pt (Clash Display, ink + one electric blue), craft.wild.as (Swiss grid tokens, hairlines, accent restraint, minus its motion weight), cloudstudio.es (warm cream monochrome, short GPU-composited motion = feels instant), Balatro (the paint-swirl, reserved for ceremony).*
