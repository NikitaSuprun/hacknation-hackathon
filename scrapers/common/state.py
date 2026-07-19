# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Cursor persistence in ops.scrape_state (one row per source)."""

import json
from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Final, Protocol, cast

from contracts.interfaces import Sink
from contracts.models import Cursor

STATE_TABLE: Final[str] = "ops.scrape_state"
STATE_KEYS: Final[tuple[str, ...]] = ("source",)
STATE_VARIANT_COLS: Final[frozenset[str]] = frozenset({"cursor"})
MAX_ERROR_LENGTH: Final[int] = 1_000


class SqlRunner(Protocol):
    """The one-statement query surface state loading needs (tools.warehouse fits)."""

    def execute(self, statement: str) -> list[tuple[object, ...]]:
        """Run one statement and fetch all rows."""
        ...


class StateStore(Protocol):
    """Load and persist one source's incremental cursor."""

    def load(self, source: str) -> Cursor | None:
        """Return the stored cursor, or None on first run."""
        ...

    def save(
        self,
        source: str,
        cursor: Cursor,
        *,
        status: str,
        error: str | None,
        items_upserted: int,
    ) -> None:
        """Persist the cursor and run outcome."""
        ...


class MemoryStateStore:
    """Dict-backed store for dry runs and unit tests; nothing leaves memory."""

    def __init__(self) -> None:
        """Start empty."""
        self.cursors: Final[dict[str, Cursor]] = {}
        self.statuses: Final[dict[str, str]] = {}

    def load(self, source: str) -> Cursor | None:
        """Return the in-memory cursor, or None when absent.

        Args:
            source: The scraper source name.

        Returns:
            The stored cursor or None.
        """
        return self.cursors.get(source)

    def save(
        self,
        source: str,
        cursor: Cursor,
        *,
        status: str,
        error: str | None,
        items_upserted: int,
    ) -> None:
        """Record the cursor and status in memory.

        Args:
            source: The scraper source name.
            cursor: The cursor to store.
            status: Run outcome ('ok' or 'error').
            error: Truncated failure message, if any.
            items_upserted: Rows written before this save.
        """
        del error, items_upserted
        self.cursors[source] = cursor
        self.statuses[source] = status


class WarehouseStateStore:
    """The live store: SELECT for load, idempotent MERGE (via the sink) for save."""

    def __init__(
        self,
        warehouse: SqlRunner,
        sink: Sink,
        catalog: str,
        *,
        clock: Callable[[], datetime],
    ) -> None:
        """Bind to one catalog; the clock is injected for testability."""
        self._warehouse: Final[SqlRunner] = warehouse
        self._sink: Final[Sink] = sink
        self._catalog: Final[str] = catalog
        self._clock: Final[Callable[[], datetime]] = clock

    def load(self, source: str) -> Cursor | None:
        """Read the cursor VARIANT back as JSON.

        Args:
            source: The scraper source name.

        Returns:
            The stored cursor, or None when the row or cursor is absent.
        """
        safe_source = source.replace("'", "''")
        rows = self._warehouse.execute(
            f"SELECT to_json(cursor) FROM {self._catalog}.{STATE_TABLE} "  # noqa: S608 - catalog/table are frozen internal identifiers
            f"WHERE source = '{safe_source}'"
        )
        if not rows or rows[0][0] is None:
            return None
        parsed: object = json.loads(str(rows[0][0]))
        if not isinstance(parsed, dict):
            return None
        state = cast("Mapping[str, object]", cast("object", parsed))
        return Cursor(source=source, state=state)

    def save(
        self,
        source: str,
        cursor: Cursor,
        *,
        status: str,
        error: str | None,
        items_upserted: int,
    ) -> None:
        """MERGE the state row through the shared sink.

        Args:
            source: The scraper source name.
            cursor: The cursor to persist.
            status: Run outcome ('ok' or 'error').
            error: Failure message, truncated for the STRING column.
            items_upserted: Rows written this run.
        """
        now = self._clock()
        row: dict[str, object] = {
            "source": source,
            "cursor": dict(cursor.state),
            "last_run_at": now,
            "last_status": status,
            "last_error": error[:MAX_ERROR_LENGTH] if error is not None else None,
            "items_upserted": items_upserted,
            "updated_at": now,
        }
        self._sink.upsert(STATE_TABLE, [row], list(STATE_KEYS), variant_cols=STATE_VARIANT_COLS)
