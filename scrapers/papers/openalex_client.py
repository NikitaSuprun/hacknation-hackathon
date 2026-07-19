# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""OpenAlex enrichment: keyed DOI-batch lookups over the pending-work queue.

Discovery is a stateless warehouse anti-join (arXiv bronze minus OpenAlex
bronze), so a failed run self-heals with no cursor repair. The lookup DOI is
the journal DOI when arXiv knows it, else the DataCite DOI arXiv registers
for every paper (10.48550/arxiv.<id>); batch misses fall back to single-work
lookups, and the final match rate is logged against the >=80% acceptance bar.
"""

from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Final, Protocol

from pydantic import ValidationError
from structlog.typing import FilteringBoundLogger

from contracts.models import BronzeRecord, Cursor, Json, RawBatch, RunResult
from scrapers.common.base import execute_run
from scrapers.common.http import HttpClient
from scrapers.common.jsonutil import as_list, as_mapping, get_list, get_str
from scrapers.common.models import RejectRow
from scrapers.common.sink import build_deps
from scrapers.common.state import SqlRunner
from scrapers.papers.models import PendingPaper
from scrapers.papers.normalize import (
    ARXIV_DOI_PREFIX,
    MissingNativeIdError,
    openalex_work_to_record,
    openalex_work_to_row,
)
from tools.db import canonical_json

OPENALEX_API: Final[str] = "https://api.openalex.org/works"
OPENALEX_BUCKET: Final[str] = "openalex"
OPENALEX_SOURCE: Final[str] = "papers.openalex"
DOI_BATCH_SIZE: Final[int] = 50
DEFAULT_PENDING_LIMIT: Final[int] = 500
NOT_FOUND_STATUS: Final[int] = 404
SPEND_HEADERS: Final[tuple[str, ...]] = (
    "x-ratelimit-remaining",
    "x-api-usage-cost",
    "x-api-usage-remaining",
)


class PendingWorks(Protocol):
    """Where the enrichment queue comes from (warehouse, fixtures, tests)."""

    def pending(self, since: date, limit: int) -> tuple[PendingPaper, ...]:
        """Return papers awaiting enrichment."""
        ...


class StaticPendingWorks:
    """A fixed queue (fixture replay and dry runs without a warehouse)."""

    def __init__(self, papers: tuple[PendingPaper, ...]) -> None:
        """Store the fixed queue."""
        self._papers: Final[tuple[PendingPaper, ...]] = papers

    def pending(self, since: date, limit: int) -> tuple[PendingPaper, ...]:
        """Return the fixed queue, capped at the limit.

        Args:
            since: Ignored.
            limit: Maximum papers to return.

        Returns:
            The queued papers.
        """
        del since
        return self._papers[:limit]


class WarehousePendingWorks:
    """The live queue: arXiv bronze anti-joined against OpenAlex bronze."""

    def __init__(self, runner: SqlRunner, catalog: str) -> None:
        """Bind to one catalog."""
        self._runner: Final[SqlRunner] = runner
        self._catalog: Final[str] = catalog

    def pending(self, since: date, limit: int) -> tuple[PendingPaper, ...]:
        """Discover un-enriched arXiv papers.

        Args:
            since: Only consider papers ingested on or after this date.
            limit: Maximum papers to return.

        Returns:
            Pending papers with their journal DOI when arXiv knows it.
        """
        rows = self._runner.execute(
            f"SELECT a.arxiv_id, CAST(a.payload:doi AS STRING) AS doi "
            f"FROM {self._catalog}.bronze.arxiv_papers_raw a "
            f"LEFT ANTI JOIN {self._catalog}.bronze.openalex_works_raw w "
            f"ON w.arxiv_id = a.arxiv_id "
            f"WHERE a.ingested_at >= '{since.isoformat()}' "
            f"LIMIT {int(limit)}"
        )
        return tuple(
            PendingPaper(arxiv_id=str(row[0]), doi=str(row[1]) if row[1] is not None else None)
            for row in rows
            if row[0] is not None
        )


def lookup_doi(paper: PendingPaper) -> str:
    """The DOI used for the OpenAlex lookup (journal DOI, else DataCite).

    Args:
        paper: The pending paper.

    Returns:
        A lowercase DOI.
    """
    if paper.doi:
        return paper.doi.lower()
    return f"{ARXIV_DOI_PREFIX}{paper.arxiv_id}".lower()


class OpenAlexClient:
    """Keyed batch and single-work lookups with spend-header logging."""

    def __init__(self, http: HttpClient, api_key: str | None, log: FilteringBoundLogger) -> None:
        """Ride the shared HttpClient (bucket 'openalex')."""
        self._http: Final[HttpClient] = http
        self._api_key: Final[str | None] = api_key
        self._log: Final[FilteringBoundLogger] = log

    def _params(self, extra: dict[str, str]) -> dict[str, str]:
        if self._api_key is not None:
            extra["api_key"] = self._api_key
        return extra

    def _log_spend(self, headers: dict[str, str]) -> None:
        spend = {name: headers[name] for name in SPEND_HEADERS if name in headers}
        if spend:
            self._log.info("openalex spend", **spend)

    def fetch_by_dois(self, dois: Sequence[str]) -> list[dict[str, Json]]:
        """One DOI-filter batch call (up to 50 DOIs).

        Args:
            dois: The lookup DOIs.

        Returns:
            The matched work objects.
        """
        response = self._http.get(
            OPENALEX_API,
            bucket=OPENALEX_BUCKET,
            params=self._params(
                {
                    "filter": "doi:" + "|".join(dois),
                    "per-page": str(DOI_BATCH_SIZE),
                }
            ),
        )
        self._log_spend(response.headers)
        body = as_mapping(response.json())
        return [as_mapping(work) for work in as_list(get_list(body, "results"))]

    def fetch_single(self, doi: str) -> dict[str, Json] | None:
        """Single-work fallback for a batch miss.

        Args:
            doi: The lookup DOI.

        Returns:
            The work object, or None when OpenAlex has no such work.
        """
        response = self._http.get(
            f"{OPENALEX_API}/https://doi.org/{doi}",
            bucket=OPENALEX_BUCKET,
            params=self._params({}),
            allow=frozenset({404}),
        )
        self._log_spend(response.headers)
        if response.status == NOT_FOUND_STATUS:
            return None
        return as_mapping(response.json())


@dataclass(frozen=True, slots=True)
class OpenAlexDeps:
    """Everything the OpenAlex scraper composes over."""

    client: OpenAlexClient
    pending: PendingWorks
    since: date
    limit: int
    clock: Callable[[], datetime]
    run_id: str
    log: FilteringBoundLogger


class OpenAlexScraper:
    """BaseScraper implementation for the OpenAlex enrichment source."""

    source: str = OPENALEX_SOURCE

    def __init__(self, deps: OpenAlexDeps) -> None:
        """Start with zeroed match counters."""
        self._deps: Final[OpenAlexDeps] = deps
        self._requested: int = 0
        self._matched: int = 0

    def fetch(self, cursor: Cursor) -> Iterator[RawBatch]:
        """Drain the pending queue in DOI batches of 50.

        Args:
            cursor: Unused (discovery is a stateless anti-join).

        Yields:
            One batch of work objects per DOI batch.
        """
        del cursor
        limit = self._deps.limit or DEFAULT_PENDING_LIMIT
        pending = self._deps.pending.pending(self._deps.since, limit)
        for start in range(0, len(pending), DOI_BATCH_SIZE):
            batch = pending[start : start + DOI_BATCH_SIZE]
            works = self._enrich_batch(batch)
            if works:
                yield RawBatch(source=OPENALEX_SOURCE, items=tuple(works))
        self._log_match_rate()

    def normalize(self, raw: RawBatch) -> list[BronzeRecord]:
        """Validate works into OpenAlex bronze rows; failures become rejects.

        Args:
            raw: One batch of work objects.

        Returns:
            Bronze records for the sink.
        """
        now = self._deps.clock()
        return [self._one(dict(item), now) for item in raw.items]

    def next_cursor(self) -> Cursor:
        """Record the run time (re-enrichment cadence bookkeeping).

        Returns:
            The cursor for ops.scrape_state.
        """
        return Cursor(
            source=OPENALEX_SOURCE,
            state={"last_run_at": self._deps.clock().isoformat()},
        )

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
        return execute_run(self, build_deps(OPENALEX_SOURCE, dry_run=dry_run), since)

    def _enrich_batch(self, batch: tuple[PendingPaper, ...]) -> list[dict[str, Json]]:
        dois = [lookup_doi(paper) for paper in batch]
        self._requested += len(dois)
        works = self._deps.client.fetch_by_dois(dois)
        found = {
            (get_str(work, "doi") or "").removeprefix("https://doi.org/").lower() for work in works
        }
        for doi in dois:
            if doi in found:
                continue
            single = self._deps.client.fetch_single(doi)
            if single is not None:
                works.append(single)
            else:
                self._deps.log.info("openalex miss", doi=doi)
        self._matched += len(works)
        return works

    def _log_match_rate(self) -> None:
        rate = self._matched / self._requested if self._requested else 0.0
        self._deps.log.info(
            "openalex match rate",
            requested=self._requested,
            matched=self._matched,
            rate=round(rate, 3),
        )

    def _one(self, work: dict[str, Json], now: datetime) -> BronzeRecord:
        try:
            openalex_work_to_record(work, now)
            row = openalex_work_to_row(work, self._deps.run_id, now, now)
        except (ValidationError, MissingNativeIdError) as exc:
            return RejectRow(
                source=OPENALEX_SOURCE,
                natural_key=get_str(work, "id") or "missing-id",
                error=str(exc),
                raw=canonical_json({"id": work.get("id"), "doi": work.get("doi")}),
                scrape_run_id=self._deps.run_id,
                ingested_at=now,
            ).to_bronze()
        return BronzeRecord(table="bronze.openalex_works_raw", row=row)
