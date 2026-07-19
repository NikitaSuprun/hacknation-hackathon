# WS-B — Papers scraper

**Owner**: 1 dev · **Timing**: ~2.5 days · **Depends on**: WS0 (T0, T3 shared lib).
**Goal**: recent papers (arXiv spine + OpenAlex enrichment) with authors, affiliations, ORCID, citations, and paper↔code links → bronze, conforming to the unified `PublicationRecord`.

**Reference**: [scrapers.md § Papers](../reference/scrapers.md) · [data-model § bronze / silver.publication](../reference/data-model.md)

## Checklist

- [ ] **P1 — arXiv client**
  - [ ] Category × date-window paging (cs.AI/LG/CL/CV/stat.ML/RO/MA/DC/DB/SE), 1 req/3s, single connection, Atom parse, cross-list dedupe
  - [ ] Code-link regex over abstract + comment (github/gitlab/huggingface)
  - [ ] Emit unified `PublicationRecord` (source-agnostic core + `source_extras`) → `bronze.arxiv_papers_raw`
  - [ ] *Acceptance*: 30-day window yields ≥2k unified records; dedupe verified; 20 extracted code links spot-checked; idempotent
- [ ] **P2 — OpenAlex enrichment**
  - [ ] Keyed DOI-batch lookups (50/call); merge authorships/institutions (ROR)/ORCID/citations; inverted-index abstract fallback → `bronze.openalex_works_raw`
  - [ ] *Acceptance*: ≥80% match rate on sample; ≥60% of matched works have ≥1 institution; spend headers logged, within $1/day free
- [ ] **P3 — PwC archive + optional S2**
  - [ ] One-time load of HF `pwc-archive/links-between-paper-and-code` → `bronze.paper_code_links`
  - [ ] Optional Semantic Scholar layer (no-op without key)
  - [ ] *Acceptance*: archive rows loaded & joinable on arxiv_id; pipeline unaffected when `S2_API_KEY` unset

## Notes & risks
- OpenAlex 2026 requires a free API key (polite pool retired); request it Day 0.
- Affiliation → education/employment is a **submission-time snapshot** and role-blind → author↔person links are candidate links with confidence, confirmed by a second signal or the interview. State this in schema comments and never present inferred employment as fact in memos.
