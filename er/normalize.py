# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Stage 0: bronze rows to person_source_record, one extractor per source.

Every derived field goes through tools.norm/tools.institutions exactly as the
fixture builder does, so fixture bronze rows normalize byte-exact into the
committed PSR fixtures. Suppressed identities (ops.erasure_suppression) are
filtered here so a re-run can never resurrect an erased person.
"""

import hashlib
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from contracts.models import BronzeRecord, Json, PersonSourceRecord, SinkValue
from scrapers.common.jsonutil import as_mapping, as_sink, get_int, get_list, get_map, get_str
from scrapers.hacknation.normalizer import (
    PEOPLE_TABLE as HACKNATION_PEOPLE_TABLE,
)
from scrapers.hacknation.normalizer import (
    PROJECTS_TABLE as HACKNATION_PROJECTS_TABLE,
)
from scrapers.hacknation.normalizer import (
    HacknationNormalizer,
    merge_psrs,
    psr_fragment_from_cv,
)
from tools import ids, institutions, norm

Row = dict[str, Json]

ORCID_URL_PREFIX: Final[str] = "https://orcid.org/"
OPENALEX_PEOPLE_URL: Final[str] = "https://api.openalex.org/people/"
HACKNATION_SOURCE: Final[str] = "hacknation"

_EMAIL: Final[re.Pattern[str]] = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_SOGC_PERSON: Final[re.Pattern[str]] = re.compile(
    r"(?P<last>[^,;.]+), (?P<first>[^,;.]+), in (?P<town>[^,;.]+), "
    r"(?P<role>[^,;.]+), mit (?P<signing>[^,;.]+)"
)
_SOGC_MARKER: Final[str] = "Eingetragene Personen:"

# Minimal deterministic gazetteer for the demo footprint; unknown locations
# simply yield no country_code (Splink treats NULL as uninformative).
_LOCATION_COUNTRIES: Final[dict[str, str]] = {
    "basel": "CH",
    "bern": "CH",
    "berlin": "DE",
    "geneva": "CH",
    "germany": "DE",
    "lausanne": "CH",
    "munich": "DE",
    "switzerland": "CH",
    "zug": "CH",
    "zurich": "CH",
}


def country_from_location(location: str | None) -> str | None:
    """Map a free-text location onto an ISO country code.

    Args:
        location: The location as observed at the source.

    Returns:
        The country code, or None when no gazetteer entry matches.
    """
    if location is None:
        return None
    for part in norm.name_norm(location).replace(",", " ").split():
        code = _LOCATION_COUNTRIES.get(part)
        if code is not None:
            return code
    return None


def _timestamps(row: Row) -> tuple[datetime, datetime]:
    scraped = datetime.fromisoformat(str(row.get("scraped_at")))
    ingested = datetime.fromisoformat(str(row.get("ingested_at")))
    return scraped, ingested


def _build(  # noqa: PLR0913 - one keyword per observed identity field, mirroring the PSR shape
    source: str,
    source_key: str,
    source_url: str,
    scraped_at: datetime,
    ingested_at: datetime,
    *,
    bronze_ref: str | None = None,
    full_name: str | None = None,
    emails: tuple[str, ...] = (),
    orcid: str | None = None,
    github_login: str | None = None,
    website_url: str | None = None,
    linkedin_url: str | None = None,
    twitter_handle: str | None = None,
    affiliation_raw: str | None = None,
    location_raw: str | None = None,
    country_code: str | None = None,
    keywords: tuple[str, ...] = (),
    bio: str | None = None,
) -> PersonSourceRecord:
    """Derive one full PSR from observed fields (the make_psr contract).

    Args:
        source: PSR source discriminator.
        source_key: Stable per-source key.
        source_url: Where the identity was observed.
        scraped_at: Source-row scrape time.
        ingested_at: Source-row ingest time.
        bronze_ref: Pointer to the bronze row of origin.
        full_name: Name as observed.
        emails: Observed emails, order-preserved.
        orcid: Bare ORCID (URL prefix stripped by the caller).
        github_login: GitHub login when the source carries one.
        website_url: Raw personal-site URL.
        linkedin_url: Raw LinkedIn profile URL (stored as observed; D7
            normalizes at match time).
        twitter_handle: Twitter/X handle.
        affiliation_raw: Affiliation as observed.
        location_raw: Location as observed.
        country_code: ISO country code.
        keywords: Topical keywords.
        bio: Free-text bio.

    Returns:
        The derived record with every normalized field populated.
    """
    email_norms = tuple(n for n in (norm.email_norm(e) for e in emails) if n is not None)
    name_norm_value = norm.name_norm(full_name) if full_name else None
    parts = name_norm_value.split() if name_norm_value else []
    return PersonSourceRecord(
        source_record_id=ids.psr_id(source, source_key),
        source=source,
        source_key=source_key,
        bronze_ref=bronze_ref,
        full_name=full_name,
        name_norm=name_norm_value,
        first_name=parts[0] if parts else None,
        last_name=parts[-1] if len(parts) > 1 else None,
        emails=emails,
        email_norms=email_norms,
        email_domain=norm.email_domain(emails[0]) if emails else None,
        orcid=orcid,
        github_login=github_login,
        website_url_norm=norm.url_norm(website_url) if website_url else None,
        linkedin_url=linkedin_url,
        twitter_handle=twitter_handle,
        affiliation_raw=affiliation_raw,
        org_norm=institutions.org_norm(affiliation_raw) if affiliation_raw else None,
        location_raw=location_raw,
        country_code=country_code,
        keywords=keywords,
        bio=bio,
        source_url=source_url,
        first_seen_at=scraped_at,
        last_seen_at=scraped_at,
        scraped_at=scraped_at,
        ingested_at=ingested_at,
    )


def _commit_emails(commits: Sequence[Row], user_id: int) -> list[str]:
    emails: list[str] = []
    for commit in commits:
        if get_int(commit, "author_user_id") != user_id:
            continue
        email = get_str(get_map(get_map(commit, "payload"), "author"), "email")
        if email is not None:
            emails.append(email)
    return emails


def _topic_keywords(commits: Sequence[Row], repos: Sequence[Row], user_id: int) -> tuple[str, ...]:
    repo_ids = {get_int(c, "repo_id") for c in commits if get_int(c, "author_user_id") == user_id}
    topics: set[str] = set()
    for repo in repos:
        if get_int(repo, "repo_id") not in repo_ids:
            continue
        payload = get_map(repo, "payload")
        topics.update(t.lower() for t in get_list(payload, "topics") if isinstance(t, str))
    return tuple(sorted(topics))


def _github_linkedin(payload: Row) -> str | None:
    """The LinkedIn URL from a GitHub profile's socialAccounts, if listed."""
    for node in get_list(get_map(payload, "socialAccounts"), "nodes"):
        if isinstance(node, dict) and get_str(node, "provider") == "LINKEDIN":
            return get_str(node, "url")
    return None


def github_psrs(
    users: Sequence[Row], commits: Sequence[Row], repos: Sequence[Row]
) -> list[PersonSourceRecord]:
    """One PSR per GitHub user; commit-author emails join the profile email.

    Args:
        users: bronze.github_users_raw rows.
        commits: bronze.github_commits_raw rows.
        repos: bronze.github_repos_raw rows.

    Returns:
        The derived records, in user order.
    """
    records: list[PersonSourceRecord] = []
    for row in users:
        user_id = get_int(row, "user_id")
        if user_id is None:
            continue
        payload = get_map(row, "payload")
        observed: list[str] = []
        profile_email = get_str(payload, "email")
        if profile_email is not None:
            observed.append(profile_email)
        observed.extend(_commit_emails(commits, user_id))
        emails = tuple(dict.fromkeys(observed))
        location = get_str(payload, "location")
        blog = get_str(payload, "blog")
        scraped, ingested = _timestamps(row)
        records.append(
            _build(
                "github",
                str(user_id),
                str(row.get("source_url")),
                scraped,
                ingested,
                bronze_ref=f"bronze.github_users_raw:user_id={user_id}",
                full_name=get_str(payload, "name") or get_str(row, "login"),
                emails=emails,
                github_login=get_str(row, "login"),
                website_url=blog or None,
                linkedin_url=_github_linkedin(payload),
                affiliation_raw=get_str(payload, "company"),
                location_raw=location,
                country_code=country_from_location(location),
                keywords=_topic_keywords(commits, repos, user_id),
                bio=get_str(payload, "bio"),
            )
        )
    return records


def _bare_orcid(orcid: str | None) -> str | None:
    if orcid is None:
        return None
    return orcid.removeprefix(ORCID_URL_PREFIX)


def openalex_author_psrs(works: Sequence[Row]) -> list[PersonSourceRecord]:
    """One PSR per distinct OpenAlex author id (their disambiguation inherited).

    Args:
        works: bronze.openalex_works_raw rows.

    Returns:
        The derived records; the first work observed for an author supplies
        its bronze_ref and affiliation.
    """
    records: list[PersonSourceRecord] = []
    seen: set[str] = set()
    for row in sorted(works, key=lambda work: str(work.get("openalex_id"))):
        work_id = get_str(row, "openalex_id")
        scraped, ingested = _timestamps(row)
        for entry in get_list(get_map(row, "payload"), "authorships"):
            if not isinstance(entry, dict):
                continue
            author = get_map(entry, "author")
            author_id = get_str(author, "id")
            if author_id is None or author_id in seen:
                continue
            seen.add(author_id)
            institutions_list = get_list(entry, "institutions")
            first = institutions_list[0] if institutions_list else None
            affiliation = get_str(first, "display_name") if isinstance(first, dict) else None
            resolved = institutions.resolve(affiliation) if affiliation else None
            records.append(
                _build(
                    "openalex_author",
                    author_id,
                    f"{OPENALEX_PEOPLE_URL}{author_id}",
                    scraped,
                    ingested,
                    bronze_ref=f"bronze.openalex_works_raw:openalex_id={work_id}",
                    full_name=get_str(author, "display_name"),
                    orcid=_bare_orcid(get_str(author, "orcid")),
                    affiliation_raw=affiliation,
                    country_code=resolved.country if resolved is not None else None,
                )
            )
    return records


def arxiv_author_psrs(papers: Sequence[Row], works: Sequence[Row]) -> list[PersonSourceRecord]:
    """PSR per (arxiv_id, position) for papers with no OpenAlex coverage.

    A contact email found in the arXiv comment attaches only to single-author
    papers - it cannot be attributed within a multi-author list.

    Args:
        papers: bronze.arxiv_papers_raw rows.
        works: bronze.openalex_works_raw rows (the coverage check).

    Returns:
        The derived fallback-spine records.
    """
    covered = {get_str(work, "arxiv_id") for work in works} - {None}
    records: list[PersonSourceRecord] = []
    for row in papers:
        arxiv_id = get_str(row, "arxiv_id")
        if arxiv_id is None or arxiv_id in covered:
            continue
        payload = get_map(row, "payload")
        authors = [a for a in get_list(payload, "authors") if isinstance(a, str)]
        comment = get_str(payload, "comment") or ""
        contact = _EMAIL.search(comment)
        scraped, ingested = _timestamps(row)
        for position, author in enumerate(authors, start=1):
            single = len(authors) == 1 and contact is not None
            records.append(
                _build(
                    "arxiv_author",
                    f"{arxiv_id}:{position}",
                    str(row.get("source_url")),
                    scraped,
                    ingested,
                    bronze_ref=f"bronze.arxiv_papers_raw:arxiv_id={arxiv_id}",
                    full_name=author,
                    emails=(contact.group(0),) if single and contact is not None else (),
                )
            )
    return records


def zefix_officer_psrs(sogc: Sequence[Row], companies: Sequence[Row]) -> list[PersonSourceRecord]:
    """PSR per (uid, name_norm) parsed from SOGC 'Eingetragene Personen' text.

    Args:
        sogc: bronze.zefix_sogc_raw rows.
        companies: bronze.zefix_companies_raw rows (the company-name lookup).

    Returns:
        The derived officer records.
    """
    names = {get_str(row, "uid"): get_str(row, "name") for row in companies}
    records: list[PersonSourceRecord] = []
    for row in sogc:
        uid = get_str(row, "uid")
        text = get_str(get_map(row, "payload"), "publicationText") or ""
        marker = text.find(_SOGC_MARKER)
        if uid is None or marker < 0:
            continue
        scraped, ingested = _timestamps(row)
        for match in _SOGC_PERSON.finditer(text[marker + len(_SOGC_MARKER) :]):
            last = match.group("last").strip()
            first = match.group("first").strip()
            records.append(
                _build(
                    "zefix_officer",
                    f"{uid}:{norm.name_norm(f'{last}, {first}')}",
                    str(row.get("source_url")),
                    scraped,
                    ingested,
                    bronze_ref=f"bronze.zefix_sogc_raw:sogc_id={get_str(row, 'sogc_id')}",
                    full_name=f"{first} {last}",
                    affiliation_raw=names.get(uid),
                    location_raw=match.group("town").strip(),
                    country_code="CH",
                )
            )
    return records


@dataclass(slots=True)
class _HacknationEnrichment:
    """Project-side facts accumulated for one Hack Nation participant."""

    linkedin_url: str | None
    keywords: set[str]
    entry: Row
    project_row: Row


def hacknation_user_id(entry: Row) -> str | None:
    """The participant key as a string (the API serves string or int ids).

    The people listing spells it user_id while project authorProfile/team
    entries spell it userId, and this is called with both shapes.
    """
    value = entry.get("user_id")
    if value is None:
        value = entry.get("userId")
    if isinstance(value, bool):
        return None
    if isinstance(value, str | int):
        return str(value)
    return None


def hacknation_member_entries(payload: Row) -> list[Row]:
    """The authorProfile plus every team[] entry of one project payload."""
    entries: list[Row] = []
    author = get_map(payload, "authorProfile")
    if author:
        entries.append(author)
    entries.extend(as_mapping(item) for item in get_list(payload, "team") if isinstance(item, dict))
    return entries


def hacknation_project_keywords(payload: Row) -> set[str]:
    """Lowercased techStack plus tags of one project payload."""
    words = {item.lower() for item in get_list(payload, "techStack") if isinstance(item, str)}
    words.update(item.lower() for item in get_list(payload, "tags") if isinstance(item, str))
    return words


def _absorb_entry(
    by_user: dict[str, _HacknationEnrichment], entry: Row, keywords: set[str], project_row: Row
) -> None:
    """Fold one author/team entry into the per-user enrichment."""
    user_id = hacknation_user_id(entry)
    if user_id is None:
        return
    found = by_user.get(user_id)
    if found is None:
        found = _HacknationEnrichment(
            linkedin_url=None, keywords=set(), entry=entry, project_row=project_row
        )
        by_user[user_id] = found
    found.keywords.update(keywords)
    if found.linkedin_url is None:
        found.linkedin_url = get_str(entry, "linkedinUrl")


def _hacknation_enrichment(projects: Sequence[Row]) -> dict[str, _HacknationEnrichment]:
    """Per-user project-side enrichment across every project payload."""
    by_user: dict[str, _HacknationEnrichment] = {}
    for row in projects:
        payload = get_map(row, "payload")
        keywords = hacknation_project_keywords(payload)
        for entry in hacknation_member_entries(payload):
            _absorb_entry(by_user, entry, keywords, row)
    return by_user


def _typed_row(row: Row) -> dict[str, SinkValue]:
    """One bronze row with its ISO temporals promoted back to datetimes.

    The sink hands the scraper typed temporals; replaying the same rows out of
    JSONL hands us strings, and the source normalizer accepts only the former.
    """
    scraped, ingested = _timestamps(row)
    typed: dict[str, SinkValue] = {key: as_sink(value) for key, value in row.items()}
    typed["scraped_at"] = scraped
    typed["ingested_at"] = ingested
    return typed


def _cv_fragments(cvs: Sequence[Row]) -> list[PersonSourceRecord]:
    """CV-derived fragments, skipping rows whose extraction never parsed."""
    fragments: list[PersonSourceRecord] = []
    for row in cvs:
        user_id = get_str(row, "user_id")
        if user_id is None:
            continue
        payload = get_map(row, "payload")
        scraped, ingested = _timestamps(row)
        fragment = psr_fragment_from_cv(
            user_id,
            payload.get("extracted"),
            source_url=str(row.get("source_url")),
            scraped_at=scraped,
            ingested_at=ingested,
        )
        if fragment is not None:
            fragments.append(fragment)
    return fragments


def hacknation_psrs(
    people: Sequence[Row], projects: Sequence[Row], cvs: Sequence[Row] = ()
) -> list[PersonSourceRecord]:
    """One PSR per unique Hack Nation participant.

    Derivation is delegated to the source's own SourceNormalizer so bronze
    replays through exactly one implementation here and in the scraper. Order
    is precedence order for the merge: people-list rows are the identity spine,
    the project side (authorProfile, team[]) enriches them, and a parsed CV
    folds in last.

    Args:
        people: bronze.hacknation_people_raw rows.
        projects: bronze.hacknation_projects_raw rows.
        cvs: bronze.hacknation_cvs_raw rows, when CV parsing ran.

    Returns:
        The merged records, one per participant, sorted by source_record_id.
    """
    normalizer = HacknationNormalizer()
    fragments: list[PersonSourceRecord] = []
    for table, rows in (
        (HACKNATION_PEOPLE_TABLE, people),
        (HACKNATION_PROJECTS_TABLE, projects),
    ):
        for row in rows:
            fragments.extend(normalizer.to_psr(BronzeRecord(table=table, row=_typed_row(row))))
    fragments.extend(_cv_fragments(cvs))
    return merge_psrs(fragments)


def suppressed_keys(suppression_rows: Iterable[Mapping[str, object]]) -> frozenset[tuple[str, str]]:
    """Load the erasure suppression set as (source, source_key_hash) pairs.

    Args:
        suppression_rows: ops.erasure_suppression rows.

    Returns:
        The suppression set.
    """
    return frozenset(
        (str(row.get("source")), str(row.get("source_key_hash"))) for row in suppression_rows
    )


def source_key_hash(source_key: str) -> str:
    """The suppression hash of one source key (sha256 hex).

    Args:
        source_key: The per-source key.

    Returns:
        The hex digest matching ops.erasure_suppression.source_key_hash.
    """
    return hashlib.sha256(source_key.encode("utf-8")).hexdigest()


def apply_suppression(
    records: Iterable[PersonSourceRecord], suppressed: frozenset[tuple[str, str]]
) -> list[PersonSourceRecord]:
    """Drop records whose identity has been erased.

    Args:
        records: Stage-0 output records.
        suppressed: The (source, source_key_hash) suppression set.

    Returns:
        The surviving records.
    """
    return [
        record
        for record in records
        if (record.source, source_key_hash(record.source_key)) not in suppressed
    ]


def normalize_bronze(
    tables: Mapping[str, list[Row]], *, suppressed: frozenset[tuple[str, str]]
) -> list[PersonSourceRecord]:
    """Run every extractor over the bronze tables and filter suppressions.

    Args:
        tables: Bronze rows keyed by schema-qualified table name.
        suppressed: The (source, source_key_hash) suppression set.

    Returns:
        All derived person source records.
    """
    records = [
        *github_psrs(
            tables.get("bronze.github_users_raw", []),
            tables.get("bronze.github_commits_raw", []),
            tables.get("bronze.github_repos_raw", []),
        ),
        *openalex_author_psrs(tables.get("bronze.openalex_works_raw", [])),
        *arxiv_author_psrs(
            tables.get("bronze.arxiv_papers_raw", []),
            tables.get("bronze.openalex_works_raw", []),
        ),
        *zefix_officer_psrs(
            tables.get("bronze.zefix_sogc_raw", []),
            tables.get("bronze.zefix_companies_raw", []),
        ),
        *hacknation_psrs(
            tables.get("bronze.hacknation_people_raw", []),
            tables.get("bronze.hacknation_projects_raw", []),
            tables.get("bronze.hacknation_cvs_raw", []),
        ),
    ]
    return apply_suppression(records, suppressed)
