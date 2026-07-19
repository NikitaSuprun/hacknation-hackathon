# Compliance — FADP/GDPR guardrails & licensing

Practical build-time guardrails (not legal advice) for Swiss revised FADP + GDPR, plus the two licensing planes. Keep this file as `docs/compliance.md` in the built repo.

## C1 — Lawful basis

Processing rests on **legitimate interest** (GDPR Art. 6(1)(f) / revFADP) for B2B deal-sourcing over manifestly public professional data, with a short documented balancing test. EDPB Guidelines 1/2024 note reasonable-expectation thresholds are lower for people acting in a professional capacity — but the controller still runs the 3-part test and owes Art. 14 notice; the "disproportionate effort" exemption is read narrowly, so we **notify at first contact**. Transparency in the first outreach email: what we collected, from which public source categories, why, and a privacy-notice link with opt-out/erasure contact. Interviews are strictly consent-based, with consent recorded verbatim in the transcript before any substantive question. This is a different risk class from LinkedIn-ToS scraping (hiQ v. LinkedIn settlement; Proxycurl shutdown 2025).

## C2 — Data minimization

Professional public signals only. **Never stored**: nationality, place-of-origin (`Heimatort`), private home addresses (Zefix parser drops them pre-bronze), special-category data. Age/gender: store only self-declared values by default; **photo-based inference is a capability behind an off-by-default flag requiring legal sign-off**; age/gender are **excluded from all scoring** either way. `avatar_url` is stored as an opaque display URL; no face/image inference by default. CVs (e.g. Hack Nation `cvUrl`): **owner decision 2026-07-19** — CV fetching **and** LLM parsing (education/experience) ship **enabled by default** for the Hack Nation source, superseding the earlier off-by-default legal-sign-off gate; opt-out via `--no-cvs`. The trade is full erasure coverage: pointers, parsed rows (`bronze.hacknation_cvs_raw`, suppression keyed by `user_id`) and the fetched volume files (path deterministic from `user_id`) are all inside the erasure cascade. Scoring prompts are instructed to ignore protected characteristics that leak through free text.

## C3 — Provenance

Every silver fact row carries `source_url` + `scraped_at`; every identity decision carries `match_method` + `evidence` + `pipeline_version`; every AI-generated field carries `*_model_version`; every memo claim carries a citation. "Where did this come from?" is answerable for any element in the UI.

## C4 — Right to erasure (`tools/erase_person.py`, single command, logged)

1. Resolve `person_id` → all `source_record_id`s (links of all statuses).
2. Gold: delete `person_features`, `venture_member`, `outreach`, `interview` rows; flag affected memos for regeneration.
3. Silver: delete `contribution`/`authorship`/`officer` for those PSRs; delete `person_connection` edges touching the person; delete links; delete PSRs; tombstone `person` (`status='erased'`, attributes nulled).
4. Bronze: delete `github_users_raw`; delete/redact `github_commits_raw` by author id / erased emails; delete `hacknation_people_raw` + `hacknation_cvs_raw` rows by `user_id` (their PSRs fall under step 3) and the CV volume file `/Volumes/{catalog}/ops/cv/hacknation/{user_id}.pdf`; `hacknation_projects_raw` rows are artifact rows — the erase executor **redacts in place** (strips the erased `user_id`'s `team[]`/`authorProfile` entries from the payload, row retained). Other artifact rows (repos/papers/companies) remain minus the deleted relationship rows.
5. Insert `ops.erasure_suppression` rows (`sha256(source_key)` per source) — scrapers + normalizer check this before every write, so re-scraping cannot resurrect the person.
6. Physical purge: set `delta.deletedFileRetentionDuration='interval 7 days'` on person-bearing tables, run `VACUUM`; record `erasure_log.vacuum_after`.
7. Write `ops.erasure_log` (requester stored only as a hash).

## C5 — Retention

Bronze payloads and non-linked persons (no venture attachment, no outreach) purged after 6 months; outreach/interview data deleted on request and at latest 12 months after last contact absent an active relationship. One scheduled cleanup job; a one-paragraph policy in the privacy notice.

## C6 — Licensing (two planes)

- **Data**: ship only CC0/CC-BY/public-register data files (Leiden CC0, ROR CC0, Crunchbase-2013 CC-BY, Wikidata CC0, Zefix/SOGC public register; Accel PDF *figures* with attribution). Hand-curate everything from restricted rankings (QS/THE/CSRankings/LinkedIn/Forbes) into our own `institution_score` table rather than redistributing their files.
- **Software**: `uv.lock`-pinned deps behind a **permissive-only allowlist** (MIT/BSD/Apache-2.0/ISC/MPL-2.0) enforced by a CI gate; denylist GPL/AGPL/SSPL and non-commercial/"source-available"; MPL/LGPL tracked; `pip-licenses` → `THIRD_PARTY_LICENSES.md` + CycloneDX SBOM regenerated each lock change. Concrete swap: RapidFuzz (MIT), not python-Levenshtein (GPL). Goal: never a copyleft obligation to open-source our code, never a non-commercial term in the graph.

## Source etiquette

Official APIs only, published rate limits, ETags, descriptive User-Agent with contact email, backoff on 429/`Retry-After`, no login-walled scraping. **LinkedIn scraping is banned in the core pipeline**; the optional self-scraper (if ever enabled) is isolated behind the `EnrichmentProvider` interface and is the user's explicit, flagged decision — a licensed provider is the compliant "responsibility-separation" path at scale. **Hack Nation**: people/project data is public and participant-disclosed on the showcase; gentle volume, public endpoints, login optional with own account, no login-walled bypass; CV fetch+parse default-on (owner decision 2026-07-19, `--no-cvs` to opt out); `hacknation` added to erasure suppression + cascade, fetched CV files included.
