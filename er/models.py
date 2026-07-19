# Copyright (c) 2026 Venture Hunt. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Value objects shared across the ER pipeline stages."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Final, cast

from contracts.models import Json

# Method precedence for link building: when several rules touch one PSR, the
# highest-priority incident rule supplies the link's method and evidence.
METHOD_PRIORITY: Final[tuple[str, ...]] = (
    "det_orcid",
    "det_email",
    "det_website",
    "det_handle",
    "det_linkedin",
    "det_crosslink",
    "det_hn_repo",
    "splink",
    "llm_adjudication",
)


@dataclass(frozen=True, slots=True)
class PsrView:
    """The matching-relevant projection of one person_source_record row."""

    source_record_id: str
    source: str
    source_key: str
    full_name: str | None
    name_norm: str | None
    first_name: str | None
    last_name: str | None
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
    avatar_url: str | None
    cv_url: str | None
    bronze_ref: str | None
    last_seen_at: str


def _text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _texts(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    items = cast("list[object]", cast("object", value))
    return tuple(item for item in items if isinstance(item, str))


def _stamp(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return value if isinstance(value, str) else ""


def psr_view(row: Mapping[str, object]) -> PsrView:
    """Project one PSR row (JSONL- or sink-shaped) onto the matching view.

    Args:
        row: A silver.person_source_record row.

    Returns:
        The typed projection.
    """
    return PsrView(
        source_record_id=_text(row.get("source_record_id")) or "",
        source=_text(row.get("source")) or "",
        source_key=_text(row.get("source_key")) or "",
        full_name=_text(row.get("full_name")),
        name_norm=_text(row.get("name_norm")),
        first_name=_text(row.get("first_name")),
        last_name=_text(row.get("last_name")),
        email_norms=_texts(row.get("email_norms")),
        email_domain=_text(row.get("email_domain")),
        orcid=_text(row.get("orcid")),
        github_login=_text(row.get("github_login")),
        website_url_norm=_text(row.get("website_url_norm")),
        linkedin_url=_text(row.get("linkedin_url")),
        twitter_handle=_text(row.get("twitter_handle")),
        affiliation_raw=_text(row.get("affiliation_raw")),
        org_norm=_text(row.get("org_norm")),
        location_raw=_text(row.get("location_raw")),
        country_code=_text(row.get("country_code")),
        keywords=_texts(row.get("keywords")),
        bio=_text(row.get("bio")),
        avatar_url=_text(row.get("avatar_url")),
        cv_url=_text(row.get("cv_url")),
        bronze_ref=_text(row.get("bronze_ref")),
        last_seen_at=_stamp(row.get("last_seen_at")),
    )


@dataclass(frozen=True, slots=True)
class RuleMatch:
    """One pairwise match decision from a deterministic, Splink, or LLM stage."""

    left: str
    right: str
    rule: str
    method: str
    confidence: float
    auto: bool
    evidence: Mapping[str, Json]


@dataclass(frozen=True, slots=True)
class ScoredPair:
    """One Splink-scored candidate pair with its comparison vector."""

    left: str
    right: str
    probability: float
    comparison: Mapping[str, Json]


@dataclass(frozen=True, slots=True)
class ReviewItem:
    """One ambiguous candidate routed to ops.er_review_queue."""

    source_record_id: str
    candidate_person_id: str
    score: float
    method: str
    features: Mapping[str, Json]
