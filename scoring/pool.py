"""Thesis to gold.candidate_pool: filters plus the tri-state funding signal.

A candidate is excluded (never deleted) with explicit reasons: sector, or
geography, or team size, or corporate OSS, or a confirmed prior raise when
the thesis demands no prior VC. Unknown geography passes — thin data lowers
confidence elsewhere, the pool filter only acts on positive mismatches.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from contracts.interfaces import LLMClient
from contracts.models import CompanyRef, SinkRow
from scoring.funding import (
    SIGNAL_CONFIRMED,
    FundingProbe,
    StaticCascadeFundedFounderResolver,
    classify_funding_signal,
)
from scoring.snapshot import Row, get_bool, get_float, require_str
from scrapers.common.jsonutil import as_sink, get_list, get_str
from tools.norm import url_norm

EU_COUNTRIES: Final[frozenset[str]] = frozenset(
    {
        "AT",
        "BE",
        "BG",
        "HR",
        "CY",
        "CZ",
        "DK",
        "EE",
        "FI",
        "FR",
        "DE",
        "GR",
        "HU",
        "IE",
        "IT",
        "LV",
        "LT",
        "LU",
        "MT",
        "NL",
        "PL",
        "PT",
        "RO",
        "SK",
        "SI",
        "ES",
        "SE",
    }
)

REASON_SECTOR: Final[str] = "sector_mismatch"
REASON_GEO: Final[str] = "geo_mismatch"
REASON_TEAM_SMALL: Final[str] = "team_too_small"
REASON_TEAM_LARGE: Final[str] = "team_too_large"
REASON_CORPORATE: Final[str] = "corporate_oss"
REASON_FUNDED: Final[str] = "confirmed_funded"


@dataclass(frozen=True, slots=True)
class PoolCandidate:
    """One venture as the pool filters see it."""

    venture_id: str
    market_tags: tuple[str, ...]
    team_size: int
    country_code: str | None
    is_corporate_oss: bool
    funding_signal: str


def _geo_matches(geographies: list[str], country: str | None) -> bool:
    if not geographies or country is None:
        return True
    return any(geo == country or (geo == "EU" and country in EU_COUNTRIES) for geo in geographies)


def _exclusion_reasons(thesis: Row, candidate: PoolCandidate) -> list[str]:
    mapping = dict(thesis)
    reasons: list[str] = []
    sectors = [item for item in get_list(mapping, "sectors") if isinstance(item, str)]
    if sectors and not set(sectors) & set(candidate.market_tags):
        reasons.append(REASON_SECTOR)
    geographies = [item for item in get_list(mapping, "geographies") if isinstance(item, str)]
    if not _geo_matches(geographies, candidate.country_code):
        reasons.append(REASON_GEO)
    min_team = get_float(thesis, "min_team")
    max_team = get_float(thesis, "max_team")
    if min_team is not None and candidate.team_size < min_team:
        reasons.append(REASON_TEAM_SMALL)
    if max_team is not None and candidate.team_size > max_team:
        reasons.append(REASON_TEAM_LARGE)
    if get_bool(thesis, "exclude_corporate_oss") is True and candidate.is_corporate_oss:
        reasons.append(REASON_CORPORATE)
    require_no_vc = get_bool(thesis, "require_no_prior_vc") is True
    if require_no_vc and candidate.funding_signal == SIGNAL_CONFIRMED:
        reasons.append(REASON_FUNDED)
    return reasons


def build_candidate_pool(
    thesis: Row, candidates: Sequence[PoolCandidate], now: datetime
) -> list[SinkRow]:
    """Materialize the candidate pool for one thesis.

    Args:
        thesis: The gold.thesis row.
        candidates: The assembled venture candidates.
        now: The pool_built_at timestamp.

    Returns:
        One row per candidate, inclusion and reasons explicit.
    """
    thesis_id = require_str(thesis, "thesis_id")
    rows: list[SinkRow] = []
    for candidate in candidates:
        reasons = _exclusion_reasons(thesis, candidate)
        reason_cells = [as_sink(reason) for reason in reasons]
        rows.append(
            {
                "thesis_id": thesis_id,
                "venture_id": candidate.venture_id,
                "included": not reasons,
                "exclusion_reasons": reason_cells,
                "funding_signal": candidate.funding_signal,
                "pool_built_at": now,
            }
        )
    return rows


@dataclass(frozen=True, slots=True)
class PoolAssembly:
    """Inputs for candidate assembly (rows plus the funding seams)."""

    ventures: tuple[Row, ...]
    members: tuple[Row, ...]
    projects: tuple[Row, ...]
    companies: tuple[Row, ...]
    resolver: StaticCascadeFundedFounderResolver
    llm: LLMClient


def _venture_project(assembly: PoolAssembly, venture: Row) -> Row | None:
    if venture.get("anchor_type") != "repo":
        return None
    anchor_id = get_str(dict(venture), "anchor_id")
    for project in assembly.projects:
        if project.get("project_id") == anchor_id:
            return project
    return None


def _venture_company(assembly: PoolAssembly, venture: Row) -> Row | None:
    website = get_str(dict(venture), "website_url")
    normalized = url_norm(website) if website else None
    for company in assembly.companies:
        company_url = get_str(dict(company), "website_url")
        if normalized is not None and company_url and url_norm(company_url) == normalized:
            return company
    return None


def _funding_texts(venture: Row, project: Row | None, company: Row | None) -> tuple[str, ...]:
    texts: list[str] = []
    for row, keys in (
        (venture, ("one_liner",)),
        (project, ("description",)),
        (company, ("purpose",)),
    ):
        if row is None:
            continue
        mapping = dict(row)
        texts.extend(value for key in keys if (value := get_str(mapping, key)) is not None)
        texts.extend(item for item in get_list(mapping, "funding_signals") if isinstance(item, str))
    return tuple(texts)


def pool_candidates(assembly: PoolAssembly) -> list[PoolCandidate]:
    """Assemble PoolCandidates from gold ventures plus silver context.

    Args:
        assembly: The rows and seams the assembly reads.

    Returns:
        One candidate per venture, funding signal computed.
    """
    candidates: list[PoolCandidate] = []
    for venture in assembly.ventures:
        venture_id = require_str(venture, "venture_id")
        project = _venture_project(assembly, venture)
        company = _venture_company(assembly, venture)
        company_ref = None
        if company is not None:
            company_map = dict(company)
            name = get_str(company_map, "name")
            if name is not None:
                company_ref = CompanyRef(
                    company_id=require_str(company, "company_id"),
                    uid=get_str(company_map, "uid"),
                    name=name,
                )
        probe = FundingProbe(
            venture_id=venture_id,
            company=company_ref,
            texts=_funding_texts(venture, project, company),
            source_url=get_str(dict(venture), "website_url") or f"venture:{venture_id}",
        )
        signal, _ = classify_funding_signal(probe, assembly.resolver, assembly.llm)
        team_size = sum(1 for row in assembly.members if row.get("venture_id") == venture_id)
        candidates.append(
            PoolCandidate(
                venture_id=venture_id,
                market_tags=tuple(
                    tag for tag in get_list(dict(venture), "market_tags") if isinstance(tag, str)
                ),
                team_size=team_size,
                country_code="CH" if company is not None else None,
                is_corporate_oss=(
                    get_bool(project, "is_corporate_oss") is True if project is not None else False
                ),
                funding_signal=signal,
            )
        )
    return candidates
