"""Source payloads to unified records and bronze rows (WS-B).

Bronze payload identity is content identity: payloads carry no volatile values
(run ids, retrieval times), so `content_hash` only changes when the science
does — including the arXiv `version` key, so a v2 always updates the row.
"""

import re
from datetime import date, datetime
from typing import Final

from contracts.models import Json, SinkRow
from scrapers.common.jsonutil import (
    as_list,
    as_mapping,
    as_sink,
    get_int,
    get_list,
    get_map,
    get_str,
)
from scrapers.papers._atom import AtomEntry
from scrapers.papers.codelinks import extract_code_links
from scrapers.papers.models import (
    SCHEMA_VERSION,
    PublicationAuthor,
    PublicationRecord,
    PublicationUrls,
)
from tools.db import content_hash
from tools.ids import publication_id

ARXIV_TABLE: Final[str] = "bronze.arxiv_papers_raw"
OPENALEX_TABLE: Final[str] = "bronze.openalex_works_raw"
S2_TABLE: Final[str] = "bronze.s2_papers_raw"
ARXIV_DOI_PREFIX: Final[str] = "10.48550/arxiv."
OPENALEX_URL_PREFIX: Final[str] = "https://openalex.org/"
DOI_URL_PREFIX: Final[str] = "https://doi.org/"
VERSION_SUFFIX_RE: Final[re.Pattern[str]] = re.compile(r"v(\d+)$")
ISO_DATE_LENGTH: Final[int] = 10
ARXIV_ABS_RE: Final[re.Pattern[str]] = re.compile(r"arxiv\.org/abs/([^\s?#]+)", re.IGNORECASE)


class MissingNativeIdError(ValueError):
    """A source item without its native id cannot become a bronze row."""

    def __init__(self, source: str) -> None:
        """Name the source in the message."""
        super().__init__(f"{source} item is missing its native id")


def split_arxiv_id(value: str) -> tuple[str, int]:
    """Split a versioned arXiv id or abs URL into (base id, version).

    Handles new-style ('2506.11111v2') and old-style ('math/0211159v1') ids;
    a missing version suffix means version 1.

    Args:
        value: An arXiv id or an arxiv.org/abs URL.

    Returns:
        The base id without version, and the version number.
    """
    tail = value.rsplit("/abs/", 1)[-1].strip()
    match = VERSION_SUFFIX_RE.search(tail)
    if match is not None:
        return tail[: match.start()], int(match.group(1))
    return tail, 1


def _published_date(published: str | None) -> date | None:
    if published is None or len(published) < ISO_DATE_LENGTH:
        return None
    try:
        return date.fromisoformat(published[:ISO_DATE_LENGTH])
    except ValueError:
        return None


def arxiv_entry_to_record(entry: AtomEntry, retrieved_at: datetime) -> PublicationRecord:
    """Build the unified record for one Atom entry (the validation gate).

    Args:
        entry: The parsed Atom entry.
        retrieved_at: When this entry was fetched.

    Returns:
        The validated PublicationRecord.

    Raises:
        MissingNativeIdError: If the entry has no id.
    """
    if entry.entry_id is None:
        raise MissingNativeIdError("arxiv")
    base_id, version = split_arxiv_id(entry.entry_id)
    code_text = "\n".join(part for part in (entry.summary, entry.comment) if part)
    return PublicationRecord(
        publication_uid=publication_id(entry.doi, base_id, None),
        data_source="arxiv",
        source_native_id=base_id,
        doi=entry.doi,
        title=entry.title,
        abstract=entry.summary or None,
        published_at=_published_date(entry.published),
        venue=None,
        categories=entry.categories,
        urls=PublicationUrls(
            landing=entry.landing_url or f"https://arxiv.org/abs/{base_id}", pdf=entry.pdf_url
        ),
        code_links=extract_code_links(code_text),
        authors=tuple(
            PublicationAuthor(
                position=index,
                full_name=name,
                orcid=None,
                source_author_id=None,
                affiliation_strings=(),
                is_corresponding=None,
            )
            for index, name in enumerate(entry.authors, start=1)
        ),
        citation_count=None,
        citation_count_source=None,
        citation_count_as_of=None,
        retrieved_at=retrieved_at,
        schema_version=SCHEMA_VERSION,
        source_extras={
            "comment": entry.comment,
            "journal_ref": entry.journal_ref,
            "primary_category": entry.primary_category,
            "version": version,
            "updated": entry.updated,
        },
    )


def arxiv_record_to_row(
    record: PublicationRecord, run_id: str, scraped_at: datetime, ingested_at: datetime
) -> SinkRow:
    """Render one arXiv record as a bronze.arxiv_papers_raw row.

    The payload keeps the committed fixture core (title, abstract, authors,
    categories, comment) plus additive keys; provenance lives in the columns.

    Args:
        record: The validated record.
        run_id: This run's scrape_run_id.
        scraped_at: Fetch timestamp.
        ingested_at: Ingestion timestamp.

    Returns:
        The row in DDL column shape.
    """
    extras = record.source_extras
    version = extras.get("version")
    payload: dict[str, Json] = {
        "title": record.title,
        "abstract": record.abstract,
        "authors": [author.full_name for author in record.authors],
        "categories": list(record.categories),
        "comment": extras.get("comment"),
        "version": version,
        "published": record.published_at.isoformat() if record.published_at else None,
        "updated": extras.get("updated"),
        "doi": record.doi,
        "journal_ref": extras.get("journal_ref"),
        "primary_category": extras.get("primary_category"),
        "links": {"landing": record.urls.landing, "pdf": record.urls.pdf},
        "code_links": [link.url for link in record.code_links],
    }
    return {
        "arxiv_id": record.source_native_id,
        "latest_version": version if isinstance(version, int) else 1,
        "payload": as_sink(payload),
        "content_hash": content_hash(payload),
        "source_url": f"https://arxiv.org/abs/{record.source_native_id}",
        "scraped_at": scraped_at,
        "ingested_at": ingested_at,
        "scrape_run_id": run_id,
    }


def reconstruct_abstract(inverted_index: dict[str, Json]) -> str:
    """Rebuild an abstract from OpenAlex's inverted index.

    Args:
        inverted_index: Word to positions mapping.

    Returns:
        The abstract text (position gaps collapse to single spaces).
    """
    positions: dict[int, str] = {}
    for word, slots in inverted_index.items():
        for slot in as_list(slots):
            if isinstance(slot, int) and not isinstance(slot, bool):
                positions[slot] = word
    return " ".join(positions[key] for key in sorted(positions))


def arxiv_id_from_work(work: dict[str, Json]) -> str | None:
    """Recover the base arXiv id from an OpenAlex work, when present.

    Args:
        work: The OpenAlex work object.

    Returns:
        The base arXiv id, or None for non-arXiv works.
    """
    doi = (get_str(work, "doi") or "").removeprefix(DOI_URL_PREFIX).lower()
    if doi.startswith(ARXIV_DOI_PREFIX):
        return split_arxiv_id(doi.removeprefix(ARXIV_DOI_PREFIX))[0]
    for location_value in get_list(work, "locations"):
        landing = get_str(as_mapping(location_value), "landing_page_url") or ""
        match = ARXIV_ABS_RE.search(landing)
        if match is not None:
            return split_arxiv_id(match.group(1))[0]
    return None


def _selected_authorships(work: dict[str, Json]) -> list[Json]:
    selected: list[Json] = []
    for authorship_value in get_list(work, "authorships"):
        authorship = as_mapping(authorship_value)
        author = get_map(authorship, "author")
        author_id = get_str(author, "id")
        selected.append(
            {
                "author": {
                    "display_name": get_str(author, "display_name"),
                    "id": author_id.removeprefix(OPENALEX_URL_PREFIX) if author_id else None,
                    "orcid": get_str(author, "orcid"),
                },
                "author_position": get_str(authorship, "author_position"),
                "institutions": [
                    {
                        "display_name": get_str(as_mapping(institution), "display_name"),
                        "ror": get_str(as_mapping(institution), "ror"),
                    }
                    for institution in get_list(authorship, "institutions")
                ],
            }
        )
    return selected


def openalex_work_to_record(work: dict[str, Json], retrieved_at: datetime) -> PublicationRecord:
    """Build the unified record for one OpenAlex work (the validation gate).

    Args:
        work: The OpenAlex work object.
        retrieved_at: When this work was fetched.

    Returns:
        The validated PublicationRecord.

    Raises:
        MissingNativeIdError: If the work has no OpenAlex id.
    """
    work_id = get_str(work, "id")
    if work_id is None:
        raise MissingNativeIdError("openalex")
    openalex_id = work_id.removeprefix(OPENALEX_URL_PREFIX)
    doi = (get_str(work, "doi") or "").removeprefix(DOI_URL_PREFIX) or None
    arxiv_id = arxiv_id_from_work(work)
    inverted = get_map(work, "abstract_inverted_index")
    authors = tuple(
        PublicationAuthor(
            position=index,
            full_name=get_str(get_map(as_mapping(authorship), "author"), "display_name") or "",
            orcid=get_str(get_map(as_mapping(authorship), "author"), "orcid"),
            source_author_id=get_str(get_map(as_mapping(authorship), "author"), "id"),
            affiliation_strings=tuple(
                name
                for institution in get_list(as_mapping(authorship), "institutions")
                if (name := get_str(as_mapping(institution), "display_name")) is not None
            ),
            is_corresponding=None,
        )
        for index, authorship in enumerate(get_list(work, "authorships"), start=1)
    )
    return PublicationRecord(
        publication_uid=publication_id(doi, arxiv_id, openalex_id),
        data_source="openalex",
        source_native_id=openalex_id,
        doi=doi,
        title=get_str(work, "display_name") or get_str(work, "title") or "",
        abstract=reconstruct_abstract(inverted) if inverted else None,
        published_at=_published_date(get_str(work, "publication_date")),
        venue=get_str(get_map(get_map(work, "primary_location"), "source"), "display_name"),
        categories=(),
        urls=PublicationUrls(landing=work_id, pdf=None),
        code_links=(),
        authors=authors,
        citation_count=get_int(work, "cited_by_count"),
        citation_count_source="openalex",
        citation_count_as_of=retrieved_at.date(),
        retrieved_at=retrieved_at,
        schema_version=SCHEMA_VERSION,
        source_extras={},
    )


def openalex_work_to_row(
    work: dict[str, Json], run_id: str, scraped_at: datetime, ingested_at: datetime
) -> SinkRow:
    """Render one OpenAlex work as a bronze.openalex_works_raw row.

    Args:
        work: The OpenAlex work object.
        run_id: This run's scrape_run_id.
        scraped_at: Fetch timestamp.
        ingested_at: Ingestion timestamp.

    Returns:
        The row in DDL column shape.

    Raises:
        MissingNativeIdError: If the work has no OpenAlex id.
    """
    work_id = get_str(work, "id")
    if work_id is None:
        raise MissingNativeIdError("openalex")
    openalex_id = work_id.removeprefix(OPENALEX_URL_PREFIX)
    inverted = get_map(work, "abstract_inverted_index")
    payload: dict[str, Json] = {
        "title": get_str(work, "display_name") or get_str(work, "title"),
        "cited_by_count": get_int(work, "cited_by_count"),
        "authorships": _selected_authorships(work),
        "abstract": reconstruct_abstract(inverted) if inverted else None,
        "publication_date": get_str(work, "publication_date"),
        "venue": get_str(get_map(get_map(work, "primary_location"), "source"), "display_name"),
    }
    return {
        "openalex_id": openalex_id,
        "doi": (get_str(work, "doi") or "").removeprefix(DOI_URL_PREFIX) or None,
        "arxiv_id": arxiv_id_from_work(work),
        "payload": as_sink(payload),
        "content_hash": content_hash(payload),
        "source_url": f"https://api.openalex.org/works/{openalex_id}",
        "scraped_at": scraped_at,
        "ingested_at": ingested_at,
        "scrape_run_id": run_id,
    }


def s2_paper_to_row(
    paper: dict[str, Json], run_id: str, scraped_at: datetime, ingested_at: datetime
) -> SinkRow:
    """Render one Semantic Scholar paper as a bronze.s2_papers_raw row.

    Args:
        paper: The S2 batch-API paper object.
        run_id: This run's scrape_run_id.
        scraped_at: Fetch timestamp.
        ingested_at: Ingestion timestamp.

    Returns:
        The row in DDL column shape.

    Raises:
        MissingNativeIdError: If the paper has no paperId.
    """
    s2_id = get_str(paper, "paperId")
    if s2_id is None:
        raise MissingNativeIdError("s2")
    external = get_map(paper, "externalIds")
    payload: dict[str, Json] = {
        "title": get_str(paper, "title"),
        "citationCount": get_int(paper, "citationCount"),
        "tldr": get_str(get_map(paper, "tldr"), "text"),
        "externalIds": external,
    }
    return {
        "s2_id": s2_id,
        "arxiv_id": get_str(external, "ArXiv"),
        "doi": get_str(external, "DOI"),
        "payload": as_sink(payload),
        "content_hash": content_hash(payload),
        "source_url": f"https://api.semanticscholar.org/graph/v1/paper/{s2_id}",
        "scraped_at": scraped_at,
        "ingested_at": ingested_at,
        "scrape_run_id": run_id,
    }
