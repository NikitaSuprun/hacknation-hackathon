# Copyright (c) 2026 Venture Hunt. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Load the fixture JSONL into dealflow_dev through the shared sink (T5).

Validates first, coerces every cell to its DDL type via the registry (no
naming heuristics, no hand-kept column lists), MERGEs each table
idempotently, then proves the three contract views return persona data.
Run twice: the second pass must report 0 inserted / 0 updated everywhere.
"""

import sys
from pathlib import Path
from typing import Final

from contracts.models import Json, SinkRow
from fixtures.build import DATA_DIR, LENA
from fixtures.validate import Tables, load_tables, validate
from tools.db import DatabricksSink
from tools.ddl_registry import coerce_rows, table_schema
from tools.settings import load_databricks_settings
from tools.warehouse import Warehouse

_VIEW_QUERIES: Final[tuple[tuple[str, str], ...]] = (
    (
        "gold.v_ranked_ventures",
        "SELECT name, round(final_score, 1), status FROM dealflow_dev.gold.v_ranked_ventures "
        "ORDER BY final_score DESC NULLS LAST",
    ),
    (
        "gold.v_venture_team",
        "SELECT venture_id, full_name, role_hint FROM dealflow_dev.gold.v_venture_team "
        "ORDER BY full_name",
    ),
    (
        "gold.v_person_signals",
        "SELECT signal_type, artifact_name FROM dealflow_dev.gold.v_person_signals "
        f"WHERE person_id = '{LENA}' ORDER BY signal_type",
    ),
)


def typed_rows(table: str, rows: list[dict[str, Json]]) -> list[SinkRow]:
    """Coerce JSONL cells to their DDL types (timestamps/dates at any depth).

    Args:
        table: Schema-qualified table name.
        rows: Rows as parsed from JSONL.

    Returns:
        New rows with temporal strings converted per the DDL registry.
    """
    return coerce_rows(table, rows)


def load_all(tables: Tables, sink: DatabricksSink) -> tuple[int, int]:
    """MERGE every fixture table into the sink's catalog.

    Merge keys and VARIANT columns come from the DDL registry, so the loader
    cannot drift from schemas/ddl.

    Args:
        tables: Parsed fixture tables.
        sink: The shared Databricks sink.

    Returns:
        Total (inserted, updated) across all tables.
    """
    inserted = 0
    updated = 0
    for table in sorted(tables):
        schema = table_schema(table)
        result = sink.upsert(
            table,
            typed_rows(table, tables[table]),
            list(schema.primary_key),
            variant_cols=schema.variant_cols,
        )
        inserted += result.inserted
        updated += result.updated
        sys.stdout.write(
            f"{table}: +{result.inserted} ~{result.updated} "
            f"={result.skipped_unchanged} !{result.suppressed}\n"
        )
    return inserted, updated


def show_views(warehouse: Warehouse) -> None:
    """Run the three contract views and print their persona rows.

    Args:
        warehouse: Warehouse connection factory.
    """
    for name, query in _VIEW_QUERIES:
        rows = warehouse.execute(query)
        sys.stdout.write(f"\n{name} ({len(rows)} rows)\n")
        for row in rows:
            sys.stdout.write(f"  {row}\n")


def main(data_dir: Path = DATA_DIR) -> int:
    """Validate, load into dealflow_dev, and prove the views (`poe fixtures-load`).

    Args:
        data_dir: The fixtures/data directory.

    Returns:
        Process exit code.
    """
    errors = validate(data_dir)
    if errors:
        for error in errors:
            sys.stderr.write(f"FIXTURE VIOLATION: {error}\n")
        return 1
    settings = load_databricks_settings()
    sink = DatabricksSink(settings, catalog="dealflow_dev")
    inserted, updated = load_all(load_tables(data_dir), sink)
    sys.stdout.write(f"\ntotal: +{inserted} inserted, ~{updated} updated\n")
    show_views(Warehouse(settings))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
