"""Sink wiring: the NullSink for dry runs and the dependency composition root.

build_deps is the only scraper code that touches Databricks constructors, and
only when dry_run is False — that is what keeps `--fixtures --dry-run` (the CI
path) credential-free.
"""

from datetime import UTC, datetime
from typing import Final

from contracts.models import SinkRow, UpsertResult
from scrapers.common.base import RunnerDeps
from scrapers.common.log import get_logger
from scrapers.common.state import MemoryStateStore, WarehouseStateStore
from tools.db import DatabricksSink
from tools.settings import load_databricks_settings
from tools.warehouse import Warehouse

DEFAULT_CATALOG: Final[str] = "dealflow_dev"


class NullSink:
    """Implements Sink without warehouse contact; records rows for inspection."""

    def __init__(self) -> None:
        """Start with no recorded rows."""
        self.rows: Final[dict[str, list[SinkRow]]] = {}

    def upsert(
        self,
        table: str,
        rows: list[SinkRow],
        keys: list[str],
        *,
        variant_cols: frozenset[str] = frozenset(),
        hash_col: str = "content_hash",
    ) -> UpsertResult:
        """Record the rows and report them all as inserted.

        Args:
            table: Schema-qualified target table.
            rows: Rows in DDL column shape.
            keys: Merge key columns (unused; kept for the protocol).
            variant_cols: VARIANT columns (unused; kept for the protocol).
            hash_col: Change-detection column (unused; kept for the protocol).

        Returns:
            Counts with every row inserted.
        """
        del keys, variant_cols, hash_col
        self.rows.setdefault(table, []).extend(rows)
        return UpsertResult(
            table=table, inserted=len(rows), updated=0, skipped_unchanged=0, suppressed=0
        )


def _utc_now() -> datetime:
    return datetime.now(UTC)


def build_deps(source: str, *, dry_run: bool, catalog: str = DEFAULT_CATALOG) -> RunnerDeps:
    """Compose the runner dependencies for one scraper invocation.

    Args:
        source: The scraper source name (used for the logger binding).
        dry_run: When True, nothing touches the warehouse — NullSink and
            an in-memory state store are used and no credentials are read.
        catalog: Target catalog for live runs.

    Returns:
        The assembled dependencies.
    """
    log = get_logger(source)
    if dry_run:
        return RunnerDeps(sink=NullSink(), state=MemoryStateStore(), warehouse=None, log=log)
    settings = load_databricks_settings()
    warehouse = Warehouse(settings)
    sink = DatabricksSink(settings, catalog)
    state = WarehouseStateStore(warehouse, sink, catalog, clock=_utc_now)
    return RunnerDeps(sink=sink, state=state, warehouse=warehouse, log=log)
