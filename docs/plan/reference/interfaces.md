# Interfaces & contracts — the parallelization backbone

Parallel work stays unblocked only if the *seams* between components are explicit, typed, versioned, and **verified before implementation**. Every seam is (a) a written contract, (b) implemented by fixtures so consumers build against it on Day 1, (c) covered by a contract test that fails CI on drift, (d) evolved additive-only. Implementation lives entirely behind the interface.

## Seams → contract artifact → owner → consumers

| Seam | Interface artifact | Owner | Consumers |
|---|---|---|---|
| Scrapers → lakehouse | bronze DDLs + `Sink.upsert` | WS0 | WS-A/B/C |
| Scraper internals | `BaseScraper`, `SourceNormalizer` ABCs | WS0 | WS-A/B/C |
| Hack Nation source | isolated script + `HacknationNormalizer(SourceNormalizer)` (+ ER rules D7/D8, `hackathon_project` anchor — all additive) | WS-G | bronze / WS-D / WS-E |
| Bronze → identities | `person_source_record` schema | WS0 | WS-D |
| ER → analytics | silver DDLs (person/facts/edges) | WS0/WS-D | WS-E |
| Analytics → product | gold **views** (`v_ranked_ventures`…) | WS0/WS-E | WS-F |
| App ↔ Databricks | proxy API contract (`/v1/*`, JSON-Schema'd) | WS-F | Lovable app |
| Career data | `EnrichmentProvider` ABC | WS-E | search-agent / PDL / self-scraper / personal-site impls |
| LLM calls | `LLMClient` ABC | WS0 | all LLM steps |
| Funding backbone | `FundedFounderResolver` ABC | WS-E | scoring |
| Scoring units | `CategoryScorer` ABC (one per 8+1 category) | WS-E | scoring orchestrator |
| Semi-structured payloads | JSON Schemas (evidence/breakdown/memo/ideal/interview) | WS0 | producers + consumers |

## Code interfaces (implementation-swappable — Protocols)

```python
class BaseScraper(Protocol):
    source: str
    def fetch(self, cursor: Cursor) -> Iterator[RawBatch]: ...
    def normalize(self, raw: RawBatch) -> list[BronzeRecord]: ...   # pydantic-validated; failures -> bronze._rejects
    def run(self, since: date, *, fixtures: bool = False, dry_run: bool = False) -> RunResult: ...

class Sink(Protocol):
    def upsert(self, table: str, rows: list[dict[str, object]], keys: list[str], *,
               variant_cols: set[str] = ..., hash_col: str = "content_hash") -> UpsertResult: ...

class SourceNormalizer(Protocol):                  # bronze row -> uniform identities
    def to_psr(self, row: BronzeRecord) -> list[PersonSourceRecord]: ...

class LLMClient(Protocol):                          # Databricks ai_query OR Anthropic direct — one swap point
    def complete(self, prompt: str, *, schema: dict[str, object] | None = None, model: str | None = None) -> LLMResponse: ...
    def embed(self, text: str) -> list[float]: ...

class EnrichmentProvider(Protocol):                 # search-agent / PDL / LinkedIn-scraper / personal-site — swappable
    name: str
    def enrich(self, ref: PersonRef) -> list[EnrichmentFact]: ...   # each: value, confidence, source_url, is_provisional

class FundedFounderResolver(Protocol):              # SOGC / Startupticker / Crunchbase — cascade composite
    def resolve(self, ref: PersonRef | CompanyRef) -> FundingStatus: ...

class InstitutionScorer(Protocol):
    def score(self, name: str, kind: Literal["university", "company"]) -> InstitutionScore: ...

class CategoryScorer(Protocol):                     # ONE impl per category 1.1.1...2.4 + ideal-match -> maximal parallelism
    category: str
    def score(self, venture: VentureView, features: FeatureBundle) -> CategoryScore: ...  # {score, evidence[], confidence, method}
```

Each `CategoryScorer`, `EnrichmentProvider`, and `FundedFounderResolver` implementation is independently ownable and testable against fixtures — that's the "many people at once" leverage: 9 category scorers behind one interface; the LinkedIn self-scraper as one isolated `EnrichmentProvider` deletable without touching scoring; the Databricks→Anthropic fallback as a second `LLMClient`.

## Why these interfaces are stable-or-cheap-to-fix

- **Additive-only evolution**: never remove/rename a field — add a nullable one; every contract carries `schema_version`/`contract_version`; a breaking change is a version bump + migration, never silent.
- **Views decouple storage from product**: UI/scoring bind to `gold.v_*` views, so base-table changes are absorbed behind the view.
- **Open extras maps**: `source_extras` (publications), `evidence`/`breakdown` VARIANT, `features` MAP → new source- or category-specific fields need no schema change.
- **Deterministic IDs**: UUIDv5 references never dangle when a producer re-runs.
- **Typed + validated at every boundary**: pydantic (Python), JSON Schema (payloads), Delta CHECK (tables) → drift caught at the boundary, not downstream.

## Verification BEFORE implementation (prove the contract on Day 1)

1. **Fixtures implement every interface** → the Day-1 fixture E2E (thesis → pool → scores → memo → UI → interview) runs to completion with *zero real implementations*. If it composes on fixtures, the contract graph is coherent — proof the interfaces are good before the real thing is built.
2. **Contract-test suite** (`tests/contracts/`, CI gate): per interface, assert (producer output validates against the schema) AND (consumer reads only declared fields / view columns) — consumer-driven, so a producer can't silently break a consumer.
3. **Single owner + Day-1 contract review**: WS0 owns shared contracts; all workstream leads sign off before the freeze; additive-only afterward.
4. **Mock proxy**: the Lovable app develops against a fixtures-backed mock of `/v1/*`, so frontend and backend proceed independently and integrate against the same JSON Schemas.
