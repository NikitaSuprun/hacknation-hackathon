# WS-C — Zefix scraper (Swiss registry)

**Owner**: 1 dev · **Timing**: ~2.5 days · **Depends on**: WS0 (T0, T3 shared lib).
**Goal**: recently registered Swiss companies (GmbH/AG) with officers and purpose text → bronze; also emit capital-increase signals that feed the funding backbone.

**Reference**: [scrapers.md § Zefix](../reference/scrapers.md) · [scoring-and-memo § funding backbone](../reference/scoring-and-memo.md) · [data-model § bronze](../reference/data-model.md)

## Checklist

- [ ] **Z1 — SHAB + Zefix clients**
  - [ ] SHAB/amtsblattportal HR list by date (`rubrics=HR`, HR01 new) + publication XML → `bronze.zefix_sogc_raw`
  - [ ] Zefix PublicREST company-by-UID (Basic auth) → `bronze.zefix_companies_raw`; opendata.swiss fallback needs no creds
  - [ ] *Acceptance*: yesterday's HR01 fully ingested; ≥90% UID→company resolution; runs without Zefix creds (fallback path)
- [ ] **Z2 — LLM extraction + classification**
  - [ ] Officers from DE/FR/IT publication text (Claude via Databricks) → `bronze.zefix_officers`-equivalent fields; `{full_name, function, signature_rights, domicile, confidence}`
  - [ ] Purpose → startup-likeness (`tech_startup_candidate|traditional|holding_shell|other`); negative-keyword short-circuit before the LLM
  - [ ] Capital-increase filings flagged for the funding backbone
  - [ ] *Acceptance*: ≥90% officer-name accuracy on a 20-publication golden set; 100% of GmbH/AG rows classified with confidence; LLM cost logged
- [ ] **Z3 — Backfill + daily mode**
  - [ ] 30-day backfill + daily 07:30 CET run; documented join key (`uid`) for the silver team
  - [ ] *Acceptance*: ~200+ GmbH/AG candidates in bronze; daily run <5 min

## Notes & risks
- **Day-0 action**: email `zefix@bj.admin.ch` for free credentials (unknown turnaround). SHAB (no auth, live-probed) + opendata.swiss cover discovery + officers if Bern is slow; Apify ($2/1k) is the paid last resort.
- Officers have no stable registry person-id → PSR keyed on `(uid, name_norm)`; ER links are confidence-scored.
- Minimization: drop `Heimatort` + private home addresses before bronze.
