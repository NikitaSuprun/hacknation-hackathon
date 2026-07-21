"""Stage 5: survivorship - golden person fields from linked source records.

Identifiers follow source precedence, names prefer completeness, affiliations
recency; conflicting sources are returned as data, never silently resolved.
The data_quality_score rewards independent corroboration: 0.5 base, +0.2 per
extra independent source, +0.1 for a lone source that carries a verified
identity (an ORCID, or OpenAlex's curated author disambiguation), capped 0.9.
"""

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from contracts.interfaces import LLMClient
from contracts.models import Json, SinkRow, SinkValue
from er.models import PsrView, psr_view
from er.normalize import HACKNATION_SOURCE, hacknation_member_entries, hacknation_user_id
from scrapers.common.jsonutil import as_sink, get_map, get_str
from tools.llm import prompt_tag

SOURCE_PRECEDENCE: Final[tuple[str, ...]] = (
    "interview",
    "github",
    "openalex_author",
    "arxiv_author",
    "enrichment",
    "zefix_officer",
    "hacknation",
)
# Sources whose facts never corroborate independently (paid/aggregated data).
DEPENDENT_SOURCES: Final[frozenset[str]] = frozenset({"enrichment"})
# Sources that carry a verified identity on their own: an ORCID holder, or an
# identity curated by OpenAlex's author disambiguation.
_CURATED_SOURCES: Final[frozenset[str]] = frozenset({"openalex_author"})

_BASE_SCORE: Final[float] = 0.5
_PER_SOURCE_BONUS: Final[float] = 0.2
_VERIFIED_BONUS: Final[float] = 0.1
_SCORE_CAP: Final[float] = 0.9

HEADLINE_TAG: Final[str] = "TASK:headline person="


@dataclass(frozen=True, slots=True)
class FieldConflict:
    """Two sources disagreeing on one canonical field; surfaced, not resolved."""

    person_id: str
    field: str
    values: tuple[str, ...]


def _precedence(source: str) -> int:
    try:
        return SOURCE_PRECEDENCE.index(source)
    except ValueError:
        return len(SOURCE_PRECEDENCE)


def _ranked(views: Sequence[PsrView]) -> list[PsrView]:
    return sorted(views, key=lambda view: (_precedence(view.source), view.source_record_id))


def _first(values: Iterable[str | None]) -> str | None:
    for value in values:
        if value is not None:
            return value
    return None


def _name_completeness(name: str) -> tuple[int, int]:
    tokens = [token.rstrip(".") for token in name.split()]
    initials = any(len(token) <= 1 for token in tokens)
    return (0 if initials else 1, len(name))


def _best_name(ranked: Sequence[PsrView]) -> str | None:
    named = [view.full_name for view in ranked if view.full_name is not None]
    if not named:
        return None
    return max(named, key=_name_completeness)


def _most_recent_affiliation(ranked: Sequence[PsrView]) -> str | None:
    holders = [view for view in ranked if view.affiliation_raw is not None]
    if not holders:
        return None
    best = max(
        holders,
        key=lambda view: (view.last_seen_at, -_precedence(view.source)),
    )
    return best.affiliation_raw


def _emails(ranked: Sequence[PsrView]) -> list[str]:
    observed: dict[str, None] = {}
    for view in ranked:
        for email in view.email_norms:
            observed.setdefault(email, None)
    return list(observed)


def independent_sources(views: Iterable[PsrView]) -> frozenset[str]:
    """Distinct source types that corroborate independently.

    Args:
        views: The person's linked PSR views.

    Returns:
        The independent source-type set (enrichment never counts).
    """
    return frozenset(view.source for view in views) - DEPENDENT_SOURCES


def data_quality_score(views: Sequence[PsrView]) -> float:
    """Corroboration-driven quality score in [0.5, 0.9].

    Args:
        views: The person's linked PSR views.

    Returns:
        The score.
    """
    independent = len(independent_sources(views))
    score = _BASE_SCORE + _PER_SOURCE_BONUS * max(independent - 1, 0)
    if independent == 1 and _has_verified_identifier(views):
        score += _VERIFIED_BONUS
    return round(min(score, _SCORE_CAP), 2)


def _has_verified_identifier(views: Sequence[PsrView]) -> bool:
    return any(view.orcid is not None or view.source in _CURATED_SOURCES for view in views)


def _avatar_url(ranked: Sequence[PsrView], bronze_users: Sequence[dict[str, Json]]) -> str | None:
    by_ref = {
        f"bronze.github_users_raw:user_id={row.get('user_id')}": get_str(
            get_map(row, "payload"), "avatar_url"
        )
        for row in bronze_users
    }
    # One pass in precedence order: a source offers its PSR column first, then
    # its bronze payload, so a low-ranked carrier never outranks a high-ranked
    # payload (hacknation sits last, github second).
    for view in ranked:
        if view.avatar_url is not None:
            return view.avatar_url
        if view.bronze_ref is not None:
            url = by_ref.get(view.bronze_ref)
            if url is not None:
                return url
    return None


def hacknation_cv_urls(hacknation_projects: Sequence[dict[str, Json]]) -> dict[str, str]:
    """cv_url pointer per Hack Nation user id (authorProfile + team entries).

    Args:
        hacknation_projects: bronze.hacknation_projects_raw rows.

    Returns:
        user_id to cvUrl for entries that carry one (first observation wins).
    """
    urls: dict[str, str] = {}
    for row in hacknation_projects:
        for entry in hacknation_member_entries(get_map(row, "payload")):
            user_id = hacknation_user_id(entry)
            cv_url = get_str(entry, "cvUrl")
            if user_id is not None and cv_url is not None:
                urls.setdefault(user_id, cv_url)
    return urls


def _cv_url(ranked: Sequence[PsrView], cv_by_user: Mapping[str, str]) -> str | None:
    """The CV pointer of the best-ranked record carrying one, if any."""
    for view in ranked:
        if view.cv_url is not None:
            return view.cv_url
        if view.source == HACKNATION_SOURCE:
            url = cv_by_user.get(view.source_key)
            if url is not None:
                return url
    return None


def _headline(person_id: str, ranked: Sequence[PsrView], llm: LLMClient) -> str | None:
    facts = "; ".join(
        f"{view.source}: {view.full_name or ''} @ {view.affiliation_raw or '?'}" for view in ranked
    )
    prompt = (
        f"{HEADLINE_TAG}{person_id}\n"
        "Write a one-line professional headline for this person from the facts.\n"
        f"Facts: {facts}"
    )
    text = llm.complete(prompt).text.strip()
    return text or None


def _conflicts(person_id: str, ranked: Sequence[PsrView]) -> list[FieldConflict]:
    conflicts: list[FieldConflict] = []
    affiliations = sorted({view.org_norm for view in ranked if view.org_norm is not None})
    if len(affiliations) > 1:
        conflicts.append(FieldConflict(person_id, "affiliation", tuple(affiliations)))
    countries = sorted({view.country_code for view in ranked if view.country_code is not None})
    if len(countries) > 1:
        conflicts.append(FieldConflict(person_id, "country_code", tuple(countries)))
    return conflicts


def build_person(  # noqa: PLR0913 - the survivorship inputs are irreducible
    person_id: str,
    views: Sequence[PsrView],
    *,
    llm: LLMClient,
    clock: Callable[[], datetime],
    bronze_users: Sequence[dict[str, Json]],
    cv_by_user: Mapping[str, str],
    created_at: datetime | None,
) -> tuple[SinkRow, list[FieldConflict]]:
    """Derive one golden silver.person row from its linked PSRs.

    Args:
        person_id: The golden person id.
        views: The person's linked PSR views.
        llm: Headline synthesizer.
        clock: Injected time source.
        bronze_users: bronze.github_users_raw rows (avatar lookup).
        cv_by_user: Hack Nation user_id to cvUrl pointer (see
            hacknation_cv_urls).
        created_at: Existing created_at to preserve, if the person exists.

    Returns:
        The person row and any field conflicts found.
    """
    ranked = _ranked(views)
    now = clock()
    emails = _emails(ranked)
    website = _first(view.website_url_norm for view in ranked)
    full_name = _best_name(ranked)
    row: SinkRow = {
        "person_id": person_id,
        "full_name": full_name,
        "display_name": full_name,
        "primary_email": emails[0] if emails else None,
        "emails": list[SinkValue](emails),
        "github_login": _first(view.github_login for view in ranked),
        "orcid": _first(view.orcid for view in ranked),
        "website_url": f"https://{website}" if website is not None else None,
        "linkedin_url": _first(view.linkedin_url for view in ranked),
        "cv_url": _cv_url(ranked, cv_by_user),
        "twitter_handle": _first(view.twitter_handle for view in ranked),
        "affiliation": _most_recent_affiliation(ranked),
        "location": _first(view.location_raw for view in ranked),
        "country_code": _first(view.country_code for view in ranked),
        "headline": _headline(person_id, ranked, llm),
        "avatar_url": _avatar_url(ranked, bronze_users),
        "data_quality_score": data_quality_score(ranked),
        "status": "active",
        "merged_into_person_id": None,
        "created_at": created_at if created_at is not None else now,
        "updated_at": now,
    }
    return row, _conflicts(person_id, ranked)


def build_persons(  # noqa: PLR0913 - the survivorship inputs are irreducible
    psr_rows: Sequence[dict[str, Json]],
    active_links: Mapping[str, str],
    *,
    llm: LLMClient,
    clock: Callable[[], datetime],
    bronze_users: Sequence[dict[str, Json]],
    hacknation_projects: Sequence[dict[str, Json]],
    existing_persons: Sequence[dict[str, Json]],
) -> tuple[list[SinkRow], list[FieldConflict]]:
    """Rebuild every golden person that holds at least one active link.

    Args:
        psr_rows: The full PSR universe.
        active_links: source_record_id to person_id for active links.
        llm: Headline synthesizer.
        clock: Injected time source.
        bronze_users: bronze.github_users_raw rows (avatar lookup).
        hacknation_projects: bronze.hacknation_projects_raw rows (cv_url
            pointer lookup).
        existing_persons: Current silver.person rows (created_at preserved).

    Returns:
        The person rows (sorted by person_id) and all field conflicts.
    """
    views_by_person: dict[str, list[PsrView]] = {}
    for row in psr_rows:
        view = psr_view(row)
        person = active_links.get(view.source_record_id)
        if person is not None:
            views_by_person.setdefault(person, []).append(view)
    created: dict[str, datetime] = {}
    for row in existing_persons:
        person = get_str(row, "person_id")
        stamp = get_str(row, "created_at")
        if person is not None and stamp is not None:
            created[person] = datetime.fromisoformat(stamp)
    persons: list[SinkRow] = []
    conflicts: list[FieldConflict] = []
    cv_by_user = hacknation_cv_urls(hacknation_projects)
    for person_id in sorted(views_by_person):
        row_built, found = build_person(
            person_id,
            views_by_person[person_id],
            llm=llm,
            clock=clock,
            bronze_users=bronze_users,
            cv_by_user=cv_by_user,
            created_at=created.get(person_id),
        )
        persons.append(row_built)
        conflicts.extend(found)
    return persons, conflicts


def backfill_person_id(
    fact_rows: Sequence[dict[str, Json]], active_links: Mapping[str, str]
) -> list[SinkRow]:
    """Refresh the denormalized person_id on fact rows; changed rows only.

    Args:
        fact_rows: contribution/authorship/officer rows.
        active_links: source_record_id to person_id for active links.

    Returns:
        Full rows whose person_id changed, ready to upsert.
    """
    changed: list[SinkRow] = []
    for row in fact_rows:
        psr = get_str(row, "source_record_id")
        if psr is None:
            continue
        person = active_links.get(psr)
        if person is not None and row.get("person_id") != person:
            updated: SinkRow = {key: as_sink(value) for key, value in row.items()}
            updated["person_id"] = person
            changed.append(updated)
    return changed


def headline_tag(person_id: str) -> str:
    """The scripting tag of one person's headline prompt.

    Args:
        person_id: The golden person id.

    Returns:
        The first prompt line (see tools.llm.prompt_tag).
    """
    return prompt_tag(f"{HEADLINE_TAG}{person_id}")
