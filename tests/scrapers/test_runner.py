# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Run-loop guarantees: batching, counts, and cursor-advance-only-on-success."""

from collections.abc import Iterator
from datetime import date
from typing import Final

import pytest

from contracts.models import BronzeRecord, Cursor, RawBatch, SinkRow, UpsertResult
from scrapers.common.base import BATCH_SIZE, RunnerDeps, execute_run
from scrapers.common.log import get_logger
from scrapers.common.models import REJECTS_TABLE
from scrapers.common.state import MemoryStateStore
from tests.scrapers.conftest import RecordingSink
from tools.db import RowShapeError

SINCE: Final[date] = date(2026, 6, 19)
REPOS_TABLE: Final[str] = "bronze.github_repos_raw"


class ScriptedScraper:
    """Emits a fixed set of bronze records through the protocol seams."""

    source: str = "github"

    def __init__(self, records: list[BronzeRecord]) -> None:
        """Store the records to emit and start recording cursors."""
        self.records: Final[list[BronzeRecord]] = records
        self.seen_cursors: Final[list[Cursor]] = []

    def fetch(self, cursor: Cursor) -> Iterator[RawBatch]:
        """Yield one marker batch after recording the cursor."""
        self.seen_cursors.append(cursor)
        yield RawBatch(source=self.source, items=({"marker": "batch"},))

    def normalize(self, raw: RawBatch) -> list[BronzeRecord]:
        """Return the scripted records."""
        del raw
        return self.records

    def next_cursor(self) -> Cursor:
        """Advance to a recognizable end-of-run cursor."""
        return Cursor(source=self.source, state={"window_end": "2026-07-19"})


def deps_with(sink: RecordingSink, state: MemoryStateStore) -> RunnerDeps:
    return RunnerDeps(sink=sink, state=state, warehouse=None, log=get_logger("test"))


def repo_record(repo_id: int) -> BronzeRecord:
    return BronzeRecord(table=REPOS_TABLE, row={"repo_id": repo_id})


def test_first_run_synthesizes_since_cursor() -> None:
    sink = RecordingSink()
    scraper = ScriptedScraper([repo_record(1)])
    execute_run(scraper, deps_with(sink, MemoryStateStore()), SINCE)
    assert scraper.seen_cursors == [Cursor(source="github", state={"since": "2026-06-19"})]


def test_flushes_at_batch_size_and_at_end() -> None:
    sink = RecordingSink()
    records = [repo_record(i) for i in range(BATCH_SIZE + 1)]
    result = execute_run(ScriptedScraper(records), deps_with(sink, MemoryStateStore()), SINCE)
    repo_calls = [call for call in sink.calls if call[0] == REPOS_TABLE]
    assert [len(call[1]) for call in repo_calls] == [BATCH_SIZE, 1]
    assert result.items_upserted == BATCH_SIZE + 1


def test_rejects_counted_separately_from_upserts() -> None:
    sink = RecordingSink()
    records = [
        repo_record(1),
        BronzeRecord(table=REJECTS_TABLE, row={"source": "github", "natural_key": "bad"}),
    ]
    result = execute_run(ScriptedScraper(records), deps_with(sink, MemoryStateStore()), SINCE)
    assert result.items_upserted == 1
    assert result.rejects == 1


def test_success_saves_next_cursor_with_ok_status() -> None:
    state = MemoryStateStore()
    deps = deps_with(RecordingSink(), state)
    result = execute_run(ScriptedScraper([repo_record(1)]), deps, SINCE)
    assert state.load("github") == Cursor(source="github", state={"window_end": "2026-07-19"})
    assert state.statuses["github"] == "ok"
    assert result.cursor == Cursor(source="github", state={"window_end": "2026-07-19"})


class ExplodingSink:
    """A Sink whose upsert always fails with a typed warehouse-side error."""

    def upsert(
        self,
        table: str,
        rows: list[SinkRow],
        keys: list[str],
        *,
        variant_cols: frozenset[str] = frozenset(),
        hash_col: str = "content_hash",
    ) -> UpsertResult:
        """Always raise."""
        del rows, keys, variant_cols, hash_col
        raise RowShapeError(table)


def test_failure_keeps_old_cursor_and_reraises() -> None:
    state = MemoryStateStore()
    old_cursor = Cursor(source="github", state={"window_end": "2026-07-01"})
    state.save("github", old_cursor, status="ok", error=None, items_upserted=0)
    deps = RunnerDeps(sink=ExplodingSink(), state=state, warehouse=None, log=get_logger("test"))
    with pytest.raises(RowShapeError, match="do not share one column set"):
        execute_run(ScriptedScraper([repo_record(1)]), deps, SINCE)
    assert state.load("github") == old_cursor
    assert state.statuses["github"] == "error"
