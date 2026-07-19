# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Hack Nation bronze rows to person_source_record fragments (the ER input).

One person surfaces in the people list plus every project they built, so the
normalizer emits one PSR fragment per sighting and merge_psrs collapses them
per source_record_id before loading - ER and scoring then consume Hack Nation
identities with zero engine changes. Field derivations mirror
fixtures.build.make_psr byte-for-byte so the golden-file contract holds.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Final

from contracts.models import BronzeRecord, Json, PersonSourceRecord, SinkValue
from tools import ids, institutions, norm

SOURCE: Final[str] = "hacknation"
PEOPLE_TABLE: Final[str] = "bronze.hacknation_people_raw"
PROJECTS_TABLE: Final[str] = "bronze.hacknation_projects_raw"
CVS_TABLE: Final[str] = "bronze.hacknation_cvs_raw"

# Only a ready-made ISO alpha-2 value is stored as country_code; anything else
# stays raw text inside location_raw (deterministic, no lookup tables).
_COUNTRY_CODE_LENGTH: Final[int] = 2


class UnsupportedTableError(ValueError):
    """Raised for bronze tables this normalizer does not own.

    A silent no-op on a wiring mistake would drop identities; failing loud is
    the contract.
    """

    def __init__(self, table: str) -> None:
        """Name the unexpected table."""
        super().__init__(f"HacknationNormalizer cannot normalize rows for {table}")


class MalformedBronzeRowError(ValueError):
    """Raised when a bronze row lacks a field the PSR contract requires."""

    def __init__(self, table: str, field: str) -> None:
        """Name the table and the unusable field."""
        super().__init__(f"{table} row has no usable {field}")


class HacknationNormalizer:
    """SourceNormalizer for Hack Nation: people and project rows to PSR fragments."""

    def to_psr(self, row: BronzeRecord) -> list[PersonSourceRecord]:
        """Extract person source records from one Hack Nation bronze row.

        Args:
            row: A bronze.hacknation_people_raw or bronze.hacknation_projects_raw
                record.

        Returns:
            Exactly one PSR for a people row; one per authorProfile/team member
            carrying a userId for a project row.

        Raises:
            UnsupportedTableError: If the row belongs to any other table.
        """
        if row.table == PEOPLE_TABLE:
            return [_people_psr(row.row)]
        if row.table == PROJECTS_TABLE:
            return _project_psrs(row.row)
        raise UnsupportedTableError(row.table)


def merge_psrs(records: Sequence[PersonSourceRecord]) -> list[PersonSourceRecord]:
    """Collapse fragments sharing source_record_id into one PSR per person.

    Input order is precedence order: the first non-null value wins per scalar
    field, list fields union with first-sighting order, the seen window widens
    to min(first_seen_at)/max(last_seen_at), and email_domain is recomputed
    from the merged emails when every winning fragment lacked it.

    Args:
        records: PSR fragments in precedence order.

    Returns:
        One merged PSR per source_record_id, sorted by source_record_id.
    """
    groups: dict[str, list[PersonSourceRecord]] = {}
    for record in records:
        groups.setdefault(record.source_record_id, []).append(record)
    return [_merge_group(group) for _, group in sorted(groups.items())]


def psr_fragment_from_cv(
    user_id: str,
    extracted: Json,
    *,
    source_url: str,
    scraped_at: datetime,
    ingested_at: datetime,
) -> PersonSourceRecord | None:
    """Minimal PSR fragment carrying CV education institutions as keywords.

    merge_psrs folds these into the person's keywords, so a parsed CV enriches
    the identity without any schema change.

    Args:
        user_id: Hack Nation user id the CV belongs to.
        extracted: CV extraction dict ({"education": [{"institution": ...}]}).
        source_url: Where the CV was fetched from.
        scraped_at: CV fetch time (tz-aware).
        ingested_at: Bronze write time (tz-aware).

    Returns:
        The fragment, or None when the CV names no institution.
    """
    keywords = _cv_institutions(extracted)
    if not keywords:
        return None
    return _to_record(
        _Fragment(
            source_key=user_id,
            bronze_ref=f"{CVS_TABLE}:user_id={user_id}",
            source_url=source_url,
            scraped_at=scraped_at,
            ingested_at=ingested_at,
            keywords=keywords,
        )
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class _Fragment:
    """Observed identity fields for one sighting; _to_record derives the rest."""

    source_key: str
    bronze_ref: str
    source_url: str
    scraped_at: datetime
    ingested_at: datetime
    full_name: str | None = None
    emails: tuple[str, ...] = ()
    linkedin_url: str | None = None
    affiliation_raw: str | None = None
    location_raw: str | None = None
    country_code: str | None = None
    keywords: tuple[str, ...] = ()
    bio: str | None = None
    avatar_url: str | None = None
    cv_url: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class _ProjectContext:
    """Per-project constants shared by every member fragment of one bronze row."""

    bronze_ref: str
    keywords: tuple[str, ...]
    source_url: str
    scraped_at: datetime
    ingested_at: datetime


def _to_record(fragment: _Fragment) -> PersonSourceRecord:
    """Derive the full PSR from a fragment, mirroring fixtures.build.make_psr."""
    email_norms = tuple(n for n in (norm.email_norm(e) for e in fragment.emails) if n is not None)
    name_norm_value = norm.name_norm(fragment.full_name) if fragment.full_name else None
    parts = name_norm_value.split() if name_norm_value else []
    affiliation = fragment.affiliation_raw
    return PersonSourceRecord(
        source_record_id=ids.psr_id(SOURCE, fragment.source_key),
        source=SOURCE,
        source_key=fragment.source_key,
        bronze_ref=fragment.bronze_ref,
        full_name=fragment.full_name,
        name_norm=name_norm_value,
        first_name=parts[0] if parts else None,
        last_name=parts[-1] if len(parts) > 1 else None,
        emails=fragment.emails,
        email_norms=email_norms,
        email_domain=norm.email_domain(fragment.emails[0]) if fragment.emails else None,
        orcid=None,
        github_login=None,
        website_url_norm=None,
        linkedin_url=fragment.linkedin_url,
        twitter_handle=None,
        affiliation_raw=affiliation,
        org_norm=institutions.org_norm(affiliation) if affiliation else None,
        location_raw=fragment.location_raw,
        country_code=fragment.country_code,
        keywords=fragment.keywords,
        bio=fragment.bio,
        source_url=fragment.source_url,
        first_seen_at=fragment.scraped_at,
        last_seen_at=fragment.scraped_at,
        scraped_at=fragment.scraped_at,
        ingested_at=fragment.ingested_at,
        avatar_url=fragment.avatar_url,
        cv_url=fragment.cv_url,
    )


def _people_psr(row: Mapping[str, SinkValue]) -> PersonSourceRecord:
    """One PSR from a people-list row (the list carries no email)."""
    payload = _require_payload(row, PEOPLE_TABLE)
    user_id = _require_key(row, PEOPLE_TABLE, "user_id")
    location_raw, country_code = _location(payload.get("city"), payload.get("country"))
    field_of_study = _text(payload.get("field_of_study"))
    full_name = _text(payload.get("display_name")) or _joined_name(
        payload.get("first_name"), payload.get("last_name")
    )
    return _to_record(
        _Fragment(
            source_key=user_id,
            bronze_ref=f"{PEOPLE_TABLE}:user_id={user_id}",
            source_url=_require_text(row, PEOPLE_TABLE, "source_url"),
            scraped_at=_require_datetime(row, PEOPLE_TABLE, "scraped_at"),
            ingested_at=_require_datetime(row, PEOPLE_TABLE, "ingested_at"),
            full_name=full_name,
            affiliation_raw=_text(payload.get("university")),
            location_raw=location_raw,
            country_code=country_code,
            keywords=(field_of_study,) if field_of_study is not None else (),
            bio=_text(payload.get("tagline")),
            avatar_url=_text(payload.get("avatar_url")),
        )
    )


def _project_psrs(row: Mapping[str, SinkValue]) -> list[PersonSourceRecord]:
    """One PSR per authorProfile/team member with a userId; others are skipped."""
    payload = _require_payload(row, PROJECTS_TABLE)
    project_key = _require_key(row, PROJECTS_TABLE, "project_id")
    context = _ProjectContext(
        bronze_ref=f"{PROJECTS_TABLE}:project_id={project_key}",
        keywords=_tech_stack(payload.get("techStack")),
        source_url=_require_text(row, PROJECTS_TABLE, "source_url"),
        scraped_at=_require_datetime(row, PROJECTS_TABLE, "scraped_at"),
        ingested_at=_require_datetime(row, PROJECTS_TABLE, "ingested_at"),
    )
    return [
        record
        for member in _members(payload)
        if (record := _member_psr(member, context)) is not None
    ]


def _members(payload: Mapping[str, SinkValue]) -> list[Mapping[str, SinkValue]]:
    """Member payloads: authorProfile first (the founder guess), then team[] in order."""
    members: list[Mapping[str, SinkValue]] = []
    author = payload.get("authorProfile")
    if isinstance(author, dict):
        members.append(author)
    team = payload.get("team")
    if isinstance(team, list):
        members.extend(entry for entry in team if isinstance(entry, dict))
    return members


def _member_psr(
    member: Mapping[str, SinkValue], context: _ProjectContext
) -> PersonSourceRecord | None:
    """One PSR per project member; None without a userId (no identity to key)."""
    user_id = _key_text(member.get("userId"))
    if user_id is None:
        return None
    email = _text(member.get("email"))
    linkedin_raw = _text(member.get("linkedinUrl"))
    location_raw, country_code = _location(member.get("city"), member.get("country"))
    full_name = _text(member.get("displayName")) or _joined_name(
        member.get("firstName"), member.get("lastName")
    )
    return _to_record(
        _Fragment(
            source_key=user_id,
            bronze_ref=context.bronze_ref,
            source_url=context.source_url,
            scraped_at=context.scraped_at,
            ingested_at=context.ingested_at,
            full_name=full_name,
            emails=(email,) if email is not None else (),
            # Normalized at ingest so ER rule D7 is plain equality cross-source.
            linkedin_url=norm.url_norm(linkedin_raw) if linkedin_raw is not None else None,
            affiliation_raw=_text(member.get("university")),
            location_raw=location_raw,
            country_code=country_code,
            keywords=context.keywords,
            avatar_url=_text(member.get("avatarUrl")),
            cv_url=_text(member.get("cvUrl")),
        )
    )


def _merge_group(group: Sequence[PersonSourceRecord]) -> PersonSourceRecord:
    """Fold one source_record_id's fragments; first non-null wins per scalar."""
    emails = _dedup(email for record in group for email in record.emails)
    email_domain = _first(record.email_domain for record in group)
    if email_domain is None and emails:
        email_domain = norm.email_domain(emails[0])
    return replace(
        group[0],
        bronze_ref=_first(record.bronze_ref for record in group),
        full_name=_first(record.full_name for record in group),
        name_norm=_first(record.name_norm for record in group),
        first_name=_first(record.first_name for record in group),
        last_name=_first(record.last_name for record in group),
        emails=emails,
        email_norms=_dedup(value for record in group for value in record.email_norms),
        email_domain=email_domain,
        orcid=_first(record.orcid for record in group),
        github_login=_first(record.github_login for record in group),
        website_url_norm=_first(record.website_url_norm for record in group),
        linkedin_url=_first(record.linkedin_url for record in group),
        twitter_handle=_first(record.twitter_handle for record in group),
        affiliation_raw=_first(record.affiliation_raw for record in group),
        org_norm=_first(record.org_norm for record in group),
        location_raw=_first(record.location_raw for record in group),
        country_code=_first(record.country_code for record in group),
        keywords=_dedup(keyword for record in group for keyword in record.keywords),
        bio=_first(record.bio for record in group),
        first_seen_at=min(record.first_seen_at for record in group),
        last_seen_at=max(record.last_seen_at for record in group),
        avatar_url=_first(record.avatar_url for record in group),
        cv_url=_first(record.cv_url for record in group),
    )


def _first[T](values: Iterable[T | None]) -> T | None:
    """First non-null value (survivorship: the earliest fragment wins)."""
    return next((value for value in values if value is not None), None)


def _dedup(values: Iterable[str]) -> tuple[str, ...]:
    """Ordered dedup; the first sighting keeps its position."""
    return tuple(dict.fromkeys(values))


def _text(value: SinkValue) -> str | None:
    """Stripped string; '' and whitespace count as absent."""
    if not isinstance(value, str):
        return None
    return value.strip() or None


def _key_text(value: SinkValue) -> str | None:
    """Source keys as strings, tolerating JSON number ids (bool is not a key)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return str(value)
    return _text(value)


def _joined_name(first: SinkValue, last: SinkValue) -> str | None:
    """Fallback full name when display_name is absent."""
    parts = [part for part in (_text(first), _text(last)) if part is not None]
    return " ".join(parts) or None


def _location(city: SinkValue, country: SinkValue) -> tuple[str | None, str | None]:
    """Split city/country into (location_raw, country_code) without lookups.

    Args:
        city: Raw city value from the payload.
        country: Raw country value; only a two-letter code becomes country_code,
            any other text folds into location_raw so no mapping table can drift.

    Returns:
        The (location_raw, country_code) pair.
    """
    city_text = _text(city)
    country_text = _text(country)
    if country_text is None:
        return city_text, None
    is_code = (
        len(country_text) == _COUNTRY_CODE_LENGTH
        and country_text.isascii()
        and country_text.isalpha()
    )
    if is_code:
        return city_text, country_text.upper()
    if city_text is None:
        return country_text, None
    return f"{city_text}, {country_text}", None


def _tech_stack(value: SinkValue) -> tuple[str, ...]:
    """The techStack list as ordered, deduped, blank-free keywords."""
    if not isinstance(value, list):
        return ()
    return _dedup(text for item in value if (text := _text(item)) is not None)


def _cv_institutions(extracted: Json) -> tuple[str, ...]:
    """Education institution names from a CV extraction dict."""
    if not isinstance(extracted, dict):
        return ()
    education = extracted.get("education")
    if not isinstance(education, list):
        return ()
    names = (entry.get("institution") for entry in education if isinstance(entry, dict))
    return _dedup(name.strip() for name in names if isinstance(name, str) and name.strip())


def _require_payload(row: Mapping[str, SinkValue], table: str) -> Mapping[str, SinkValue]:
    """The VARIANT payload as a mapping.

    Args:
        row: The bronze row.
        table: The bronze table name, for the error message.

    Returns:
        The payload mapping.

    Raises:
        MalformedBronzeRowError: If the payload is not an object.
    """
    payload = row.get("payload")
    if not isinstance(payload, dict):
        raise MalformedBronzeRowError(table, "payload")
    return payload


def _require_key(row: Mapping[str, SinkValue], table: str, field: str) -> str:
    """A non-blank key column, stringified.

    Args:
        row: The bronze row.
        table: The bronze table name, for the error message.
        field: The key column name.

    Returns:
        The key as a string.

    Raises:
        MalformedBronzeRowError: If the key is missing or blank.
    """
    key = _key_text(row.get(field))
    if key is None:
        raise MalformedBronzeRowError(table, field)
    return key


def _require_text(row: Mapping[str, SinkValue], table: str, field: str) -> str:
    """A non-blank string column.

    Args:
        row: The bronze row.
        table: The bronze table name, for the error message.
        field: The column name.

    Returns:
        The stripped string value.

    Raises:
        MalformedBronzeRowError: If the value is missing or blank.
    """
    text = _text(row.get(field))
    if text is None:
        raise MalformedBronzeRowError(table, field)
    return text


def _require_datetime(row: Mapping[str, SinkValue], table: str, field: str) -> datetime:
    """A tz-typed timestamp column.

    Args:
        row: The bronze row.
        table: The bronze table name, for the error message.
        field: The column name.

    Returns:
        The datetime value.

    Raises:
        MalformedBronzeRowError: If the value is not a datetime.
    """
    value = row.get(field)
    if not isinstance(value, datetime):
        raise MalformedBronzeRowError(table, field)
    return value
