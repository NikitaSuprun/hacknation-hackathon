# Copyright (c) 2026 Venture Hunt. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Frozen value objects crossing the workstream seams.

These shapes are contract surface: evolve them additive-only after the Day-1
freeze (add optional fields; never remove or rename).
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime

type Json = str | int | float | bool | None | list[Json] | dict[str, Json]
"""A parsed JSON value; the honest type for payloads, evidence, and raw rows."""

type SinkValue = (
    str | int | float | bool | None | datetime | date | list[SinkValue] | dict[str, SinkValue]
)
"""One sink cell: JSON shape plus typed temporals, at any nesting depth."""

type SinkRow = dict[str, SinkValue]
"""One row in DDL column shape, as the Sink accepts it."""


@dataclass(frozen=True, slots=True)
class Cursor:
    """Per-source incremental position, persisted in ops.scrape_state."""

    source: str
    state: Mapping[str, Json]


@dataclass(frozen=True, slots=True)
class RawBatch:
    """One fetched batch of raw source payloads."""

    source: str
    items: tuple[Mapping[str, Json], ...]


@dataclass(frozen=True, slots=True)
class BronzeRecord:
    """A validated row destined for one bronze table."""

    table: str
    row: Mapping[str, SinkValue]


@dataclass(frozen=True, slots=True)
class RunResult:
    """Outcome summary of one scraper run."""

    source: str
    items_upserted: int
    rejects: int
    cursor: Cursor | None


@dataclass(frozen=True, slots=True)
class UpsertResult:
    """Counts from one idempotent MERGE."""

    table: str
    inserted: int
    updated: int
    skipped_unchanged: int
    suppressed: int


@dataclass(frozen=True, slots=True)
class PersonSourceRecord:
    """One per-source identity: the immutable ER input (silver.person_source_record)."""

    source_record_id: str
    source: str
    source_key: str
    bronze_ref: str | None
    full_name: str | None
    name_norm: str | None
    first_name: str | None
    last_name: str | None
    emails: tuple[str, ...]
    email_norms: tuple[str, ...]
    email_domain: str | None
    orcid: str | None
    github_login: str | None
    website_url_norm: str | None
    linkedin_url: str | None
    twitter_handle: str | None
    affiliation_raw: str | None
    org_norm: str | None
    location_raw: str | None
    country_code: str | None
    keywords: tuple[str, ...]
    bio: str | None
    source_url: str
    first_seen_at: datetime
    last_seen_at: datetime
    scraped_at: datetime
    ingested_at: datetime
    avatar_url: str | None = None
    cv_url: str | None = None

    def to_row(self) -> SinkRow:
        """Render as a sink-loadable row in DDL column order (tuples become lists).

        Returns:
            A column-name to value mapping matching the DDL.
        """
        return {
            "source_record_id": self.source_record_id,
            "source": self.source,
            "source_key": self.source_key,
            "bronze_ref": self.bronze_ref,
            "full_name": self.full_name,
            "name_norm": self.name_norm,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "emails": list(self.emails),
            "email_norms": list(self.email_norms),
            "email_domain": self.email_domain,
            "orcid": self.orcid,
            "github_login": self.github_login,
            "website_url_norm": self.website_url_norm,
            "linkedin_url": self.linkedin_url,
            "twitter_handle": self.twitter_handle,
            "affiliation_raw": self.affiliation_raw,
            "org_norm": self.org_norm,
            "location_raw": self.location_raw,
            "country_code": self.country_code,
            "keywords": list(self.keywords),
            "bio": self.bio,
            "source_url": self.source_url,
            "first_seen_at": self.first_seen_at,
            "last_seen_at": self.last_seen_at,
            "scraped_at": self.scraped_at,
            "ingested_at": self.ingested_at,
            "avatar_url": self.avatar_url,
            "cv_url": self.cv_url,
        }


@dataclass(frozen=True, slots=True)
class PersonRef:
    """The identifiers an enrichment or funding lookup may key on."""

    person_id: str
    full_name: str | None
    github_login: str | None
    orcid: str | None
    website_url: str | None
    linkedin_url: str | None


@dataclass(frozen=True, slots=True)
class CompanyRef:
    """A company as seen by the funding backbone."""

    company_id: str
    uid: str | None
    name: str


@dataclass(frozen=True, slots=True)
class EnrichmentFact:
    """One provider-sourced fact; provisional until independently corroborated."""

    field: str
    value: str
    confidence: float
    source_url: str
    is_provisional: bool
    provider: str


@dataclass(frozen=True, slots=True)
class FundingStatus:
    """Verdict of the funded-founder cascade."""

    funded: bool
    stage: str | None
    amount_chf: int | None
    as_of: date | None
    source: str | None


@dataclass(frozen=True, slots=True)
class InstitutionScore:
    """A calibrated 0-100 institution score (gold.institution_score row)."""

    institution_id: str
    kind: str
    canonical_name: str
    score: float
    prestige: float | None
    outcome: float | None


@dataclass(frozen=True, slots=True)
class Evidence:
    """The uniform evidence element cited by scores and memos."""

    claim: str
    source_url: str
    source_type: str | None
    snippet: str | None
    weight: float | None


@dataclass(frozen=True, slots=True)
class CategoryScore:
    """One category verdict; score None means N/A (weight is redistributed)."""

    category: str
    score: float | None
    confidence: float
    method: str
    rationale: str | None
    evidence: tuple[Evidence, ...]


@dataclass(frozen=True, slots=True)
class VentureView:
    """The venture snapshot handed to category scorers."""

    venture_id: str
    name: str
    one_liner: str | None
    anchor_type: str
    member_person_ids: tuple[str, ...]
    extras: Mapping[str, Json]


@dataclass(frozen=True, slots=True)
class FeatureBundle:
    """The shared calibrated feature layer for one venture's members."""

    person_features: Mapping[str, Mapping[str, float]]
    venture_features: Mapping[str, float]


@dataclass(frozen=True, slots=True)
class LLMResponse:
    """One model completion, parsed when a schema was requested."""

    text: str
    parsed: Mapping[str, Json] | None
    model: str
