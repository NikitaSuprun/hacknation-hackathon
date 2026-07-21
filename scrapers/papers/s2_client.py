"""Optional Semantic Scholar layer: a clean no-op when S2_API_KEY is unset."""

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import date, datetime
from typing import Final

from structlog.typing import FilteringBoundLogger

from contracts.models import BronzeRecord, Cursor, Json, RawBatch, RunResult
from scrapers.common.base import execute_run
from scrapers.common.http import HttpClient
from scrapers.common.jsonutil import as_list, as_mapping
from scrapers.common.models import RejectRow
from scrapers.common.sink import build_deps
from scrapers.papers.normalize import MissingNativeIdError, s2_paper_to_row
from scrapers.papers.openalex_client import PendingWorks
from tools.db import canonical_json

S2_BATCH_URL: Final[str] = "https://api.semanticscholar.org/graph/v1/paper/batch"
S2_BUCKET: Final[str] = "s2"
S2_SOURCE: Final[str] = "papers.s2"
S2_BATCH_SIZE: Final[int] = 500
S2_FIELDS: Final[str] = "externalIds,citationCount,tldr,title"
DEFAULT_PENDING_LIMIT: Final[int] = 500


@dataclass(frozen=True, slots=True)
class S2Deps:
    """Everything the S2 scraper composes over; api_key None means disabled."""

    http: HttpClient
    api_key: str | None
    pending: PendingWorks
    since: date
    limit: int
    clock: Callable[[], datetime]
    run_id: str
    log: FilteringBoundLogger


class S2Scraper:
    """BaseScraper implementation for the optional Semantic Scholar source."""

    source: str = S2_SOURCE

    def __init__(self, deps: S2Deps) -> None:
        """Bind the dependencies."""
        self._deps: Final[S2Deps] = deps

    def fetch(self, cursor: Cursor) -> Iterator[RawBatch]:
        """Batch-fetch papers by arXiv id; yields nothing without a key.

        Args:
            cursor: Unused (the queue comes from the pending seam).

        Yields:
            One batch of paper objects per 500-id POST.
        """
        del cursor
        if self._deps.api_key is None:
            self._deps.log.info("s2 disabled: no S2_API_KEY set")
            return
        limit = self._deps.limit or DEFAULT_PENDING_LIMIT
        pending = self._deps.pending.pending(self._deps.since, limit)
        for start in range(0, len(pending), S2_BATCH_SIZE):
            batch = pending[start : start + S2_BATCH_SIZE]
            response = self._deps.http.post_json(
                S2_BATCH_URL,
                {"ids": [f"ARXIV:{paper.arxiv_id}" for paper in batch]},
                bucket=S2_BUCKET,
                params={"fields": S2_FIELDS},
            )
            papers = [as_mapping(paper) for paper in as_list(response.json())]
            yield RawBatch(source=S2_SOURCE, items=tuple(paper for paper in papers if paper))

    def normalize(self, raw: RawBatch) -> list[BronzeRecord]:
        """Validate papers into S2 bronze rows; failures become rejects.

        Args:
            raw: One batch of paper objects.

        Returns:
            Bronze records for the sink.
        """
        now = self._deps.clock()
        return [self._one(dict(item), now) for item in raw.items]

    def next_cursor(self) -> Cursor:
        """Record the run time.

        Returns:
            The cursor for ops.scrape_state.
        """
        return Cursor(source=S2_SOURCE, state={"last_run_at": self._deps.clock().isoformat()})

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
        return execute_run(self, build_deps(S2_SOURCE, dry_run=dry_run), since)

    def _one(self, paper: dict[str, Json], now: datetime) -> BronzeRecord:
        try:
            row = s2_paper_to_row(paper, self._deps.run_id, now, now)
        except MissingNativeIdError as exc:
            return RejectRow(
                source=S2_SOURCE,
                natural_key="missing-id",
                error=str(exc),
                raw=canonical_json({"title": paper.get("title")}),
                scrape_run_id=self._deps.run_id,
                ingested_at=now,
            ).to_bronze()
        return BronzeRecord(table="bronze.s2_papers_raw", row=row)
