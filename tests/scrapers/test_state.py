# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Cursor persistence: load parses the VARIANT, save merges through the sink."""

from datetime import UTC, datetime
from typing import Final

from contracts.models import Cursor
from scrapers.common.state import MemoryStateStore, WarehouseStateStore
from tests.scrapers.conftest import RecordingSink

FROZEN_NOW: Final[datetime] = datetime(2026, 7, 19, 12, 0, 0, tzinfo=UTC)


class FakeRunner:
    """A SqlRunner answering a canned result."""

    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        """Store the canned rows."""
        self.rows: Final[list[tuple[object, ...]]] = rows
        self.statements: Final[list[str]] = []

    def execute(self, statement: str) -> list[tuple[object, ...]]:
        """Record the statement and return the canned rows."""
        self.statements.append(statement)
        return self.rows


def test_memory_store_roundtrip() -> None:
    store = MemoryStateStore()
    assert store.load("github") is None
    cursor = Cursor(source="github", state={"window_end": "2026-07-19"})
    store.save("github", cursor, status="ok", error=None, items_upserted=5)
    assert store.load("github") == cursor
    assert store.statuses["github"] == "ok"


def test_warehouse_load_parses_variant_json() -> None:
    runner = FakeRunner([('{"window_end": "2026-07-18"}',)])
    store = WarehouseStateStore(runner, RecordingSink(), "dealflow_dev", clock=lambda: FROZEN_NOW)
    cursor = store.load("github")
    assert cursor == Cursor(source="github", state={"window_end": "2026-07-18"})
    assert runner.statements == [
        "SELECT to_json(cursor) FROM dealflow_dev.ops.scrape_state WHERE source = 'github'"
    ]


def test_warehouse_load_absent_row_is_none() -> None:
    runner = FakeRunner([])
    store = WarehouseStateStore(runner, RecordingSink(), "dealflow_dev", clock=lambda: FROZEN_NOW)
    assert store.load("github") is None


def test_warehouse_save_merges_state_row() -> None:
    sink = RecordingSink()
    store = WarehouseStateStore(FakeRunner([]), sink, "dealflow_dev", clock=lambda: FROZEN_NOW)
    cursor = Cursor(source="github", state={"window_end": "2026-07-19"})
    store.save("github", cursor, status="error", error="x" * 2000, items_upserted=7)
    table, rows, keys, variant_cols = sink.calls[0]
    assert table == "ops.scrape_state"
    assert keys == ["source"]
    assert variant_cols == frozenset({"cursor"})
    assert rows[0]["cursor"] == {"window_end": "2026-07-19"}
    assert rows[0]["last_status"] == "error"
    error_value = rows[0]["last_error"]
    assert isinstance(error_value, str)
    assert len(error_value) == 1000
    assert rows[0]["items_upserted"] == 7
    assert rows[0]["last_run_at"] == FROZEN_NOW
