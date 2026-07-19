# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""The shared run loop: fetch -> normalize -> buffered upserts -> cursor advance.

At-least-once fetch plus idempotent MERGE gives effectively-exactly-once
ingestion; the cursor advances only after every buffered upsert has returned,
so a failed run replays from the previous cursor.
"""

import contextlib
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from typing import Protocol

from structlog.typing import FilteringBoundLogger

from contracts.interfaces import Sink
from contracts.models import BronzeRecord, Cursor, RawBatch, RunResult
from scrapers.common.state import StateStore
from scrapers.common.tables import BATCH_SIZE, MERGE_KEYS, REJECTS_TABLE, VARIANT_COLS
from tools.warehouse import Warehouse


class RunnableScraper(Protocol):
    """What the runner needs beyond BaseScraper: the end-of-run cursor."""

    source: str

    def fetch(self, cursor: Cursor) -> Iterator[RawBatch]:
        """Yield raw batches from the source, starting at the cursor."""
        ...

    def normalize(self, raw: RawBatch) -> list[BronzeRecord]:
        """Validate raw items into bronze rows; failures become reject rows."""
        ...

    def next_cursor(self) -> Cursor:
        """Render the cursor to persist after a fully successful run."""
        ...


@dataclass(frozen=True, slots=True)
class RunnerDeps:
    """Everything execute_run needs; dry runs carry no warehouse."""

    sink: Sink
    state: StateStore
    warehouse: Warehouse | None
    log: FilteringBoundLogger


@dataclass(slots=True)
class _RunTally:
    upserted: int
    rejects: int


def _flush(deps: RunnerDeps, table: str, rows: list[dict[str, object]], tally: _RunTally) -> None:
    if not rows:
        return
    result = deps.sink.upsert(
        table, rows, list(MERGE_KEYS[table]), variant_cols=VARIANT_COLS.get(table, frozenset())
    )
    if table == REJECTS_TABLE:
        tally.rejects += len(rows)
    else:
        tally.upserted += result.inserted + result.updated
    deps.log.info(
        "flush",
        table=table,
        staged=len(rows),
        inserted=result.inserted,
        updated=result.updated,
        skipped_unchanged=result.skipped_unchanged,
        suppressed=result.suppressed,
    )
    rows.clear()


def _drain(
    deps: RunnerDeps,
    scraper: RunnableScraper,
    cursor: Cursor,
    buffers: dict[str, list[dict[str, object]]],
    tally: _RunTally,
) -> None:
    for batch in scraper.fetch(cursor):
        for record in scraper.normalize(batch):
            rows = buffers.setdefault(record.table, [])
            rows.append(dict(record.row))
            if len(rows) >= BATCH_SIZE:
                _flush(deps, record.table, rows, tally)
    for table, rows in buffers.items():
        _flush(deps, table, rows, tally)


def execute_run(scraper: RunnableScraper, deps: RunnerDeps, since: date) -> RunResult:
    """Run one scraper end to end and persist its cursor on success.

    Args:
        scraper: The source scraper to drive.
        deps: Sink, state store, and logger.
        since: Backfill start used when no cursor is stored yet.

    Returns:
        The run summary with the newly persisted cursor.

    Raises:
        Exception: Whatever fetch/normalize/upsert raised; the old cursor is
            kept (best-effort saved with status 'error') before re-raising.
    """
    cursor = deps.state.load(scraper.source) or Cursor(
        source=scraper.source, state={"since": since.isoformat()}
    )
    buffers: dict[str, list[dict[str, object]]] = {}
    tally = _RunTally(0, 0)
    try:
        _drain(deps, scraper, cursor, buffers, tally)
    except Exception as exc:
        with contextlib.suppress(Exception):
            deps.state.save(
                scraper.source,
                cursor,
                status="error",
                error=str(exc),
                items_upserted=tally.upserted,
            )
        raise
    new_cursor = scraper.next_cursor()
    deps.state.save(
        scraper.source, new_cursor, status="ok", error=None, items_upserted=tally.upserted
    )
    return RunResult(
        source=scraper.source,
        items_upserted=tally.upserted,
        rejects=tally.rejects,
        cursor=new_cursor,
    )
