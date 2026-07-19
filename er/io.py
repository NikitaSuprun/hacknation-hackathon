# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Row sources and the registry-driven sink fan-out for the ER pipeline.

SQL identifiers here are DDL-contract table names plus a catalog guarded by
require_identifier, which is what makes the per-file S608 ignore safe.
"""

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Final, Protocol

from contracts.interfaces import Sink
from contracts.models import Json, SinkRow, UpsertResult
from scrapers.common.jsonutil import as_mapping
from scrapers.common.state import SqlRunner, require_identifier
from tools.ddl_registry import table_schema


class RowSource(Protocol):
    """Uniform read access to one table's rows, fixture- or warehouse-backed."""

    def rows(self, table: str) -> list[dict[str, Json]]:
        """Return every row of the table (empty when the table has no data)."""
        ...


class FixtureRowSource:
    """Reads `{table}.jsonl` files from a fixtures data directory."""

    def __init__(self, data_dir: Path) -> None:
        """Bind the directory holding one JSONL file per table."""
        self._data_dir: Final[Path] = data_dir

    def rows(self, table: str) -> list[dict[str, Json]]:
        """Parse the table's JSONL file.

        Args:
            table: Schema-qualified table name.

        Returns:
            The parsed rows; empty when the file does not exist.
        """
        path = self._data_dir / f"{table}.jsonl"
        if not path.exists():
            return []
        lines = path.read_text(encoding="utf-8").splitlines()
        return [as_mapping(json.loads(line)) for line in lines if line.strip()]


class WarehouseRowSource:
    """Reads live tables as JSON rows through a SqlRunner."""

    def __init__(self, runner: SqlRunner, catalog: str) -> None:
        """Bind the runner to one catalog (identifier-guarded)."""
        self._runner: Final[SqlRunner] = runner
        self._catalog: Final[str] = require_identifier(catalog)

    def rows(self, table: str) -> list[dict[str, Json]]:
        """SELECT the whole table, one canonical-JSON object per row.

        Args:
            table: Schema-qualified table name (identifier-guarded).

        Returns:
            The parsed rows.
        """
        safe_table = require_identifier(table)
        fetched = self._runner.execute(
            f"SELECT to_json(struct(*)) FROM {self._catalog}.{safe_table}"
        )
        return [as_mapping(json.loads(str(row[0]))) for row in fetched if row and row[0]]


def sink_all(sink: Sink, tables: Mapping[str, list[SinkRow]]) -> dict[str, UpsertResult]:
    """Upsert every produced table through the shared sink.

    Merge keys and VARIANT columns come from the DDL registry, never from
    hand-kept lists.

    Args:
        sink: The lakehouse writer.
        tables: Rows per schema-qualified table name.

    Returns:
        The per-table upsert results (empty tables are skipped).
    """
    results: dict[str, UpsertResult] = {}
    for table in sorted(tables):
        rows = tables[table]
        if not rows:
            continue
        schema = table_schema(table)
        results[table] = sink.upsert(
            table, rows, list(schema.primary_key), variant_cols=schema.variant_cols
        )
    return results
