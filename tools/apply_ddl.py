# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Apply the layered DDLs (schemas/ddl/*.sql) to one or both catalogs, idempotently.

Delta rejects re-adding an existing constraint, so those errors are treated as
no-ops; anything else is a real failure.
"""

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from tools.settings import load_databricks_settings
from tools.warehouse import CursorLike, Warehouse, WarehouseError

DDL_DIR: Final[Path] = Path(__file__).resolve().parent.parent / "schemas" / "ddl"
DEFAULT_CATALOGS: Final[tuple[str, str]] = ("dealflow_dev", "dealflow")

_SKIPPABLE_STATEMENT_MARKER: Final[str] = "ADD CONSTRAINT"
_ALREADY_EXISTS_MARKERS: Final[tuple[str, ...]] = ("already exists", "ALREADY_EXISTS")


@dataclass(frozen=True, slots=True)
class ApplyResult:
    """Statement counts for one catalog pass."""

    executed: int
    skipped: int


def render(sql_text: str, catalog: str) -> str:
    """Substitute the ${catalog} parameter.

    Args:
        sql_text: Raw DDL file content.
        catalog: Target catalog name.

    Returns:
        Executable SQL text.
    """
    return sql_text.replace("${catalog}", catalog)


def _strip_line_comments(sql_text: str) -> str:
    """Drop `--` line comments so semicolons inside them cannot split statements.

    Args:
        sql_text: SQL text, possibly with line comments.

    Returns:
        The text with every `--`-to-end-of-line span removed. Our DDL files
        never place `--` inside a string literal, so a plain scan is safe.
    """
    lines: list[str] = []
    for line in sql_text.splitlines():
        index = line.find("--")
        lines.append(line if index < 0 else line[:index].rstrip())
    return "\n".join(lines)


def split_statements(sql_text: str) -> list[str]:
    """Split a DDL file into executable statements.

    Args:
        sql_text: SQL text, possibly with line comments.

    Returns:
        Non-empty statements with comments stripped.
    """
    statements: list[str] = []
    for chunk in _strip_line_comments(sql_text).split(";"):
        stripped = chunk.strip()
        if stripped:
            statements.append(stripped)
    return statements


def is_skippable_error(statement: str, error_message: str) -> bool:
    """Decide whether a failed statement is an idempotent-re-run no-op.

    Args:
        statement: The statement that failed.
        error_message: The error text from the warehouse.

    Returns:
        True for re-added constraints that already exist.
    """
    if _SKIPPABLE_STATEMENT_MARKER not in statement.upper():
        return False
    return any(marker in error_message for marker in _ALREADY_EXISTS_MARKERS)


def _execute_statement(cursor: CursorLike, statement: str) -> bool:
    """Run one statement; report False when skipped as already-applied."""
    try:
        cursor.execute(statement)
    except WarehouseError as error:
        if not is_skippable_error(statement, str(error)):
            raise
        return False
    return True


def _apply_file(cursor: CursorLike, path: Path, catalog: str) -> tuple[int, int]:
    """Run one rendered DDL file; return (executed, skipped) counts."""
    executed = 0
    skipped = 0
    for statement in split_statements(render(path.read_text(encoding="utf-8"), catalog)):
        if _execute_statement(cursor, statement):
            executed += 1
        else:
            skipped += 1
    return executed, skipped


def apply_catalog(warehouse: Warehouse, catalog: str, ddl_dir: Path = DDL_DIR) -> ApplyResult:
    """Apply every DDL file, in name order, to one catalog.

    Args:
        warehouse: Warehouse connection factory.
        catalog: Target catalog name.
        ddl_dir: Directory of numbered .sql files.

    Returns:
        Counts of executed and skipped statements.
    """
    executed = 0
    skipped = 0
    with warehouse.cursor() as cursor:
        for path in sorted(ddl_dir.glob("*.sql")):
            file_executed, file_skipped = _apply_file(cursor, path, catalog)
            executed += file_executed
            skipped += file_skipped
    return ApplyResult(executed=executed, skipped=skipped)


def main(argv: list[str] | None = None) -> int:
    """Apply the DDLs to the requested catalogs.

    Args:
        argv: CLI arguments; defaults to sys.argv.

    Returns:
        Process exit code.
    """
    parser = argparse.ArgumentParser(description="Apply schemas/ddl to Unity Catalog.")
    parser.add_argument(
        "--catalog",
        action="append",
        choices=list(DEFAULT_CATALOGS),
        help="target catalog; repeatable (default: both)",
    )
    args = parser.parse_args(argv)
    catalogs: list[str] = args.catalog or list(DEFAULT_CATALOGS)

    warehouse = Warehouse(load_databricks_settings())
    for catalog in catalogs:
        result = apply_catalog(warehouse, catalog)
        sys.stdout.write(
            f"{catalog}: executed {result.executed} statements, "
            f"skipped {result.skipped} already-applied\n"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
