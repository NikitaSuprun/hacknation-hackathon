# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""The arXiv spine: category x 3-day-slice paging at 1 request per 3 seconds.

Compliance: single connection, >=3s between requests (the 'arxiv' token
bucket), descriptive User-Agent. Slices keep offsets shallow because deep
paging on the arXiv API is flaky; an empty page with results outstanding is
retried once. Cross-listed papers dedupe on base id within a run.
"""

import dataclasses
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Final

from pydantic import TypeAdapter, ValidationError
from structlog.typing import FilteringBoundLogger

from contracts.models import BronzeRecord, Cursor, Json, RawBatch, RunResult
from scrapers.common.base import execute_run
from scrapers.common.http import HttpClient
from scrapers.common.models import RejectRow
from scrapers.common.sink import build_deps
from scrapers.papers._atom import AtomEntry, parse_atom
from scrapers.papers.normalize import (
    MissingNativeIdError,
    arxiv_entry_to_record,
    arxiv_record_to_row,
    split_arxiv_id,
)
from tools.db import canonical_json

ARXIV_API: Final[str] = "https://export.arxiv.org/api/query"
ARXIV_BUCKET: Final[str] = "arxiv"
ARXIV_SOURCE: Final[str] = "papers.arxiv"
CATEGORIES: Final[tuple[str, ...]] = (
    "cs.AI",
    "cs.LG",
    "cs.CL",
    "cs.CV",
    "stat.ML",
    "cs.RO",
    "cs.MA",
    "cs.DC",
    "cs.DB",
    "cs.SE",
)
PAGE_SIZE: Final[int] = 200
WINDOW_SLICE_DAYS: Final[int] = 3
WINDOW_OVERLAP_DAYS: Final[int] = 1
ATOM_ADAPTER: Final[TypeAdapter[AtomEntry]] = TypeAdapter(AtomEntry)


def _stamp(day: date, *, end_of_day: bool) -> str:
    return f"{day:%Y%m%d}2359" if end_of_day else f"{day:%Y%m%d}0000"


def slice_windows(start: date, end: date) -> Iterator[tuple[date, date]]:
    """Split [start, end] into slices of at most WINDOW_SLICE_DAYS days.

    Args:
        start: Window start (inclusive).
        end: Window end (inclusive).

    Yields:
        (slice_start, slice_end) date pairs.
    """
    cursor = start
    while cursor <= end:
        slice_end = min(cursor + timedelta(days=WINDOW_SLICE_DAYS - 1), end)
        yield cursor, slice_end
        cursor = slice_end + timedelta(days=1)


class ArxivClient:
    """Typed paging over the arXiv Atom API."""

    def __init__(self, http: HttpClient) -> None:
        """Ride the shared HttpClient (bucket 'arxiv', 1 req / 3s)."""
        self._http: Final[HttpClient] = http

    def query(
        self, category: str, start: date, end: date, offset: int
    ) -> tuple[tuple[AtomEntry, ...], int]:
        """Fetch one page of a category x date-window query.

        Args:
            category: One arXiv category ('cs.LG').
            start: Slice start date.
            end: Slice end date.
            offset: Result offset (paging).

        Returns:
            Parsed entries and the reported total; an empty page with results
            outstanding is retried once (a known arXiv API flake).
        """
        entries, total = self._query_once(category, start, end, offset)
        if not entries and total > offset:
            entries, total = self._query_once(category, start, end, offset)
        return entries, total

    def _query_once(
        self, category: str, start: date, end: date, offset: int
    ) -> tuple[tuple[AtomEntry, ...], int]:
        window = f"[{_stamp(start, end_of_day=False)} TO {_stamp(end, end_of_day=True)}]"
        response = self._http.get(
            ARXIV_API,
            bucket=ARXIV_BUCKET,
            params={
                "search_query": f"cat:{category} AND submittedDate:{window}",
                "sortBy": "submittedDate",
                "sortOrder": "ascending",
                "start": str(offset),
                "max_results": str(PAGE_SIZE),
            },
        )
        return parse_atom(response.body)


@dataclass(frozen=True, slots=True)
class ArxivDeps:
    """Everything the arXiv scraper composes over."""

    client: ArxivClient
    since: date
    limit: int
    clock: Callable[[], datetime]
    run_id: str
    log: FilteringBoundLogger


class ArxivScraper:
    """BaseScraper implementation for the arXiv source."""

    source: str = ARXIV_SOURCE

    def __init__(self, deps: ArxivDeps) -> None:
        """Start with an empty cross-list dedupe set."""
        self._deps: Final[ArxivDeps] = deps
        self._seen: Final[set[str]] = set()
        self._window_end: date = deps.since

    def fetch(self, cursor: Cursor) -> Iterator[RawBatch]:
        """Walk every category over the window, deduping cross-lists.

        Args:
            cursor: The stored cursor ({'window_end': iso-date}).

        Yields:
            One batch per fetched page (already deduped on base id).
        """
        start = self._start_date(cursor)
        self._window_end = self._deps.clock().date()
        for category in CATEGORIES:
            if self._limit_reached():
                return
            yield from self._category_batches(category, start, self._window_end)

    def normalize(self, raw: RawBatch) -> list[BronzeRecord]:
        """Validate entries into arXiv bronze rows; failures become rejects.

        Args:
            raw: One fetched page of Atom entry mappings.

        Returns:
            Bronze records for the sink.
        """
        now = self._deps.clock()
        return [self._one(dict(item), now) for item in raw.items]

    def next_cursor(self) -> Cursor:
        """Advance the window end after a fully successful run.

        Returns:
            The cursor for the next incremental run.
        """
        return Cursor(source=ARXIV_SOURCE, state={"window_end": self._window_end.isoformat()})

    def run(self, since: date, *, fixtures: bool = False, dry_run: bool = False) -> RunResult:
        """Satisfy BaseScraper by delegating to the shared runner.

        Args:
            since: Backfill start date.
            fixtures: Replay checked-in fixtures instead of live HTTP.
            dry_run: Skip all warehouse contact.

        Returns:
            The run summary.
        """
        del fixtures
        return execute_run(self, build_deps(ARXIV_SOURCE, dry_run=dry_run), since)

    def _start_date(self, cursor: Cursor) -> date:
        stored = cursor.state.get("window_end")
        if isinstance(stored, str):
            return date.fromisoformat(stored) - timedelta(days=WINDOW_OVERLAP_DAYS)
        return self._deps.since

    def _limit_reached(self) -> bool:
        return 0 < self._deps.limit <= len(self._seen)

    def _category_batches(self, category: str, start: date, end: date) -> Iterator[RawBatch]:
        for slice_start, slice_end in slice_windows(start, end):
            if self._limit_reached():
                return
            yield from self._slice_pages(category, slice_start, slice_end)

    def _slice_pages(self, category: str, start: date, end: date) -> Iterator[RawBatch]:
        offset = 0
        while not self._limit_reached():
            entries, total = self._deps.client.query(category, start, end, offset)
            fresh = self._fresh(entries)
            if fresh:
                yield RawBatch(
                    source=ARXIV_SOURCE,
                    items=tuple(dataclasses.asdict(entry) for entry in fresh),
                )
            offset += PAGE_SIZE
            if len(entries) < PAGE_SIZE or offset >= total:
                return

    def _fresh(self, entries: tuple[AtomEntry, ...]) -> list[AtomEntry]:
        fresh: list[AtomEntry] = []
        for entry in entries:
            # Id-less (malformed) entries dedupe on title so overlapping
            # slices produce exactly one reject row, not one per slice.
            if entry.entry_id is not None:
                key = split_arxiv_id(entry.entry_id)[0]
            else:
                key = f"noid:{entry.title}"
            if key in self._seen:
                continue
            self._seen.add(key)
            fresh.append(entry)
        return fresh

    def _one(self, item: dict[str, Json], now: datetime) -> BronzeRecord:
        try:
            entry = ATOM_ADAPTER.validate_python(item)
            record = arxiv_entry_to_record(entry, now)
        except (ValidationError, MissingNativeIdError) as exc:
            return RejectRow(
                source=ARXIV_SOURCE,
                natural_key=str(item.get("entry_id") or "missing-id"),
                error=str(exc),
                raw=canonical_json(item),
                scrape_run_id=self._deps.run_id,
                ingested_at=now,
            ).to_bronze()
        return BronzeRecord(
            table="bronze.arxiv_papers_raw",
            row=arxiv_record_to_row(record, self._deps.run_id, now, now),
        )
