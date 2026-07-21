"""The single feedparser touchpoint: Atom XML to typed AtomEntry values.

feedparser ships no type stubs; its FeedParserDict is a dict subclass, so all
access is laundered through the shared jsonutil narrowers and none of its
unknown types leak past this module.
"""

from dataclasses import dataclass
from typing import cast

import feedparser  # pyright: ignore[reportMissingTypeStubs] - vendor ships no stubs

from contracts.models import Json
from scrapers.common.jsonutil import as_mapping, get_list, get_map, get_str


@dataclass(frozen=True, slots=True)
class AtomEntry:
    """One arXiv Atom entry, reduced to the fields WS-B consumes.

    entry_id is None for malformed entries missing their id; normalization
    turns those into bronze._rejects rows instead of crashing the run.
    """

    entry_id: str | None
    title: str
    summary: str
    authors: tuple[str, ...]
    categories: tuple[str, ...]
    primary_category: str | None
    comment: str | None
    journal_ref: str | None
    doi: str | None
    published: str | None
    updated: str | None
    landing_url: str | None
    pdf_url: str | None


def _links(entry: dict[str, Json]) -> tuple[str | None, str | None]:
    landing: str | None = None
    pdf: str | None = None
    for link_value in get_list(entry, "links"):
        link = as_mapping(link_value)
        href = get_str(link, "href")
        if href is None:
            continue
        if get_str(link, "rel") == "alternate":
            landing = href
        if get_str(link, "type") == "application/pdf" or get_str(link, "title") == "pdf":
            pdf = href
    return landing, pdf


def _entry(raw: dict[str, Json]) -> AtomEntry:
    landing, pdf = _links(raw)
    title = get_str(raw, "title") or ""
    return AtomEntry(
        entry_id=get_str(raw, "id"),
        title=" ".join(title.split()),
        summary=(get_str(raw, "summary") or "").strip(),
        authors=tuple(
            name
            for author in get_list(raw, "authors")
            if (name := get_str(as_mapping(author), "name")) is not None
        ),
        categories=tuple(
            term
            for tag in get_list(raw, "tags")
            if (term := get_str(as_mapping(tag), "term")) is not None
        ),
        primary_category=get_str(get_map(raw, "arxiv_primary_category"), "term"),
        comment=get_str(raw, "arxiv_comment"),
        journal_ref=get_str(raw, "arxiv_journal_ref"),
        doi=get_str(raw, "arxiv_doi"),
        published=get_str(raw, "published"),
        updated=get_str(raw, "updated"),
        landing_url=landing,
        pdf_url=pdf,
    )


def parse_atom(xml: bytes) -> tuple[tuple[AtomEntry, ...], int]:
    """Parse one Atom page into entries plus the opensearch total.

    Args:
        xml: The raw Atom response body.

    Returns:
        Entries and the reported total result count for the query.
    """
    parsed = feedparser.parse(xml)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType] - vendor API is untyped
    document = as_mapping(cast("object", parsed))  # pyright: ignore[reportUnknownArgumentType] - laundered via the object seam
    feed = get_map(document, "feed")
    total_text = get_str(feed, "opensearch_totalresults") or "0"
    total = int(total_text) if total_text.isdigit() else 0
    entries = tuple(_entry(as_mapping(raw)) for raw in get_list(document, "entries"))
    return entries, total
