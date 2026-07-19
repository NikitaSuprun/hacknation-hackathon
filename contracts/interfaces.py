# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""The eight Protocols that decouple the workstreams (see reference/interfaces.md).

Implementations live entirely behind these seams: fixtures implement every one
on Day 1, so consumers never wait for real code. Evolution is additive-only.
"""

from collections.abc import Iterator, Mapping
from datetime import date
from typing import Literal, Protocol

from contracts.models import (
    BronzeRecord,
    CategoryScore,
    CompanyRef,
    Cursor,
    EnrichmentFact,
    FeatureBundle,
    FundingStatus,
    InstitutionScore,
    LLMResponse,
    PersonRef,
    PersonSourceRecord,
    RawBatch,
    RunResult,
    UpsertResult,
    VentureView,
)


class BaseScraper(Protocol):
    """A source scraper: fetch raw batches, normalize, write bronze idempotently."""

    source: str

    def fetch(self, cursor: Cursor) -> Iterator[RawBatch]:
        """Yield raw batches from the source, starting at the cursor."""
        ...

    def normalize(self, raw: RawBatch) -> list[BronzeRecord]:
        """Validate raw items into bronze rows; failures go to bronze._rejects."""
        ...

    def run(self, since: date, *, fixtures: bool = False, dry_run: bool = False) -> RunResult:
        """Execute fetch -> normalize -> upsert and advance the cursor on success."""
        ...


class Sink(Protocol):
    """The lakehouse writer every producer shares (implemented by tools/db.py)."""

    def upsert(
        self,
        table: str,
        rows: list[dict[str, object]],
        keys: list[str],
        *,
        variant_cols: frozenset[str] = frozenset(),
        hash_col: str = "content_hash",
    ) -> UpsertResult:
        """Idempotently MERGE rows on keys, skipping unchanged content hashes."""
        ...


class SourceNormalizer(Protocol):
    """Bronze row to uniform per-source identities (the ER input)."""

    def to_psr(self, row: BronzeRecord) -> list[PersonSourceRecord]:
        """Extract zero or more person source records from one bronze row."""
        ...


class LLMClient(Protocol):
    """One swap point for Databricks ai_query versus the Anthropic API."""

    def complete(
        self,
        prompt: str,
        *,
        schema: Mapping[str, object] | None = None,
        model: str | None = None,
    ) -> LLMResponse:
        """Run one completion, JSON-schema-constrained when a schema is given."""
        ...

    def embed(self, text: str) -> list[float]:
        """Return the 1024-dim L2-normalized embedding for the text."""
        ...


class EnrichmentProvider(Protocol):
    """A career-data provider; each implementation is isolated and rip-out-able."""

    name: str

    def enrich(self, ref: PersonRef) -> list[EnrichmentFact]:
        """Return provider facts for the person; always provisional on arrival."""
        ...


class FundedFounderResolver(Protocol):
    """The funding backbone: has this person/company already raised?"""

    def resolve(self, ref: PersonRef | CompanyRef) -> FundingStatus:
        """Cascade through the funding sources and return the best verdict."""
        ...


class InstitutionScorer(Protocol):
    """Lookup into the calibrated institution table (home of MIT > KTH)."""

    def score(self, name: str, kind: Literal["university", "company"]) -> InstitutionScore:
        """Resolve a raw institution name to its calibrated score."""
        ...


class CategoryScorer(Protocol):
    """One implementation per rubric category plus ideal-match: the parallel unit."""

    category: str

    def score(self, venture: VentureView, features: FeatureBundle) -> CategoryScore:
        """Score one venture for this category with cited evidence."""
        ...
