# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Authoritative table schemas parsed from schemas/ddl/*.sql.

Column types, merge keys, and staging schemas must come from the DDL contract
itself - never from naming heuristics or hand-maintained registries that can
drift. Parsed once per process; the DDLs are our own, so the grammar is the
subset they actually use.
"""

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from functools import cache
from pathlib import Path
from typing import Final, Literal, cast

from contracts.models import Json, SinkRow, SinkValue

DDL_DIR: Final[Path] = Path(__file__).resolve().parent.parent / "schemas" / "ddl"

type ScalarKind = Literal[
    "string", "bigint", "int", "double", "float", "boolean", "timestamp", "date", "variant"
]


@dataclass(frozen=True, slots=True)
class Scalar:
    """A scalar DDL type."""

    kind: ScalarKind


@dataclass(frozen=True, slots=True)
class Array:
    """ARRAY<element>."""

    element: "DdlType"


@dataclass(frozen=True, slots=True)
class MapType:
    """MAP<key, value>."""

    key: "DdlType"
    value: "DdlType"


@dataclass(frozen=True, slots=True)
class Struct:
    """STRUCT<name: type, ...> with field order preserved."""

    fields: tuple[tuple[str, "DdlType"], ...]


type DdlType = Scalar | Array | MapType | Struct


class UnknownTableError(KeyError):
    """Raised when a table is not defined in schemas/ddl."""

    def __init__(self, table: str) -> None:
        """Name the missing table."""
        super().__init__(f"{table} is not defined in schemas/ddl")


class UnknownColumnError(KeyError):
    """Raised when a column is not defined for a DDL table."""

    def __init__(self, table: str, column: str) -> None:
        """Name the missing column."""
        super().__init__(f"{table} has no column {column} in schemas/ddl")


class DdlParseError(ValueError):
    """Raised when a DDL fragment does not match the expected grammar."""

    def __init__(self, fragment: str) -> None:
        """Quote the offending fragment."""
        super().__init__(f"cannot parse DDL fragment: {fragment!r}")


@dataclass(frozen=True, slots=True)
class TableSchema:
    """One table's contract: ordered columns, types, and primary key."""

    name: str
    columns: tuple[tuple[str, DdlType], ...]
    primary_key: tuple[str, ...]

    def column_type(self, column: str) -> DdlType:
        """Type of one column.

        Args:
            column: Column name.

        Returns:
            The parsed DDL type.

        Raises:
            UnknownColumnError: If the column is not in the DDL.
        """
        for name, ddl_type in self.columns:
            if name == column:
                return ddl_type
        raise UnknownColumnError(self.name, column)

    @property
    def column_names(self) -> tuple[str, ...]:
        """Column names in DDL order."""
        return tuple(name for name, _ in self.columns)

    @property
    def variant_cols(self) -> frozenset[str]:
        """Columns whose type is VARIANT (staged as canonical-JSON strings)."""
        return frozenset(
            name for name, ddl_type in self.columns if ddl_type == Scalar(kind="variant")
        )

    @property
    def complex_cols(self) -> frozenset[str]:
        """ARRAY/MAP/STRUCT columns (compared via to_json, never directly)."""
        return frozenset(
            name for name, ddl_type in self.columns if not isinstance(ddl_type, Scalar)
        )


_SCALARS: Final[dict[str, ScalarKind]] = {
    "STRING": "string",
    "BIGINT": "bigint",
    "INT": "int",
    "DOUBLE": "double",
    "FLOAT": "float",
    "BOOLEAN": "boolean",
    "TIMESTAMP": "timestamp",
    "DATE": "date",
    "VARIANT": "variant",
}

_CREATE_TABLE: Final[re.Pattern[str]] = re.compile(
    r"CREATE TABLE IF NOT EXISTS\s+([a-z_][\w.]*)\s*\(", re.IGNORECASE
)
_PRIMARY_KEY: Final[re.Pattern[str]] = re.compile(r"PRIMARY KEY\s*\(([^)]*)\)", re.IGNORECASE)
_COMMENT: Final[re.Pattern[str]] = re.compile(r"--[^\n]*")
_TYPE_END: Final[re.Pattern[str]] = re.compile(r"\s+(?:NOT\s|DEFAULT\s|COMMENT\s)", re.IGNORECASE)


def _split_top_level(text: str, separator: str) -> list[str]:
    """Split on a separator at zero paren/angle-bracket depth."""
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for char in text:
        if char in "(<":
            depth += 1
        elif char in ")>":
            depth -= 1
        if char == separator and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
    parts.append("".join(current))
    return [part.strip() for part in parts if part.strip()]


def parse_type(text: str) -> DdlType:
    """Parse one DDL type expression.

    Args:
        text: The type text, e.g. `MAP<STRING,BIGINT>`.

    Returns:
        The parsed type tree.

    Raises:
        DdlParseError: If the text is not a supported DDL type.
    """
    stripped = text.strip()
    upper = stripped.upper()
    if upper in _SCALARS:
        return Scalar(kind=_SCALARS[upper])
    if upper.startswith("ARRAY<") and stripped.endswith(">"):
        return Array(element=parse_type(stripped[6:-1]))
    if upper.startswith("MAP<") and stripped.endswith(">"):
        key_text, value_text = _split_top_level(stripped[4:-1], ",")
        return MapType(key=parse_type(key_text), value=parse_type(value_text))
    if upper.startswith("STRUCT<") and stripped.endswith(">"):
        fields: list[tuple[str, DdlType]] = []
        for field_text in _split_top_level(stripped[7:-1], ","):
            field_name, _, field_type = field_text.partition(":")
            if not field_type:
                raise DdlParseError(field_text)
            fields.append((field_name.strip(), parse_type(field_type)))
        return Struct(fields=tuple(fields))
    raise DdlParseError(stripped)


def _table_body(sql: str, start: int) -> str:
    """Return the balanced-paren body starting at the opening paren."""
    depth = 0
    for index in range(start, len(sql)):
        if sql[index] == "(":
            depth += 1
        elif sql[index] == ")":
            depth -= 1
            if depth == 0:
                return sql[start + 1 : index]
    raise DdlParseError(sql[start : start + 80])


@dataclass(frozen=True, slots=True)
class _Column:
    name: str
    ddl_type: DdlType


@dataclass(frozen=True, slots=True)
class _PrimaryKey:
    columns: tuple[str, ...]


def _parse_item(item: str) -> _Column | _PrimaryKey | None:
    """Parse one body item into a column, a primary key, or nothing."""
    if item.upper().startswith("CONSTRAINT"):
        match = _PRIMARY_KEY.search(item)
        if match is None:
            return None
        return _PrimaryKey(tuple(column.strip() for column in match.group(1).split(",")))
    name, _, rest = item.partition(" ")
    end = _TYPE_END.search(rest)
    type_text = rest[: end.start()] if end else rest
    return _Column(name=name.strip(), ddl_type=parse_type(type_text))


def _parse_table(name: str, body: str) -> TableSchema:
    columns: list[tuple[str, DdlType]] = []
    primary_key: tuple[str, ...] = ()
    for item in _split_top_level(body, ","):
        match _parse_item(item):
            case _Column(name=column, ddl_type=ddl_type):
                columns.append((column, ddl_type))
            case _PrimaryKey(columns=key_columns):
                primary_key = key_columns
            case None:
                pass
    return TableSchema(name=name, columns=tuple(columns), primary_key=primary_key)


@cache
def registry(ddl_dir: Path = DDL_DIR) -> dict[str, TableSchema]:
    """Parse every CREATE TABLE in the DDL directory.

    Args:
        ddl_dir: Directory of numbered .sql files.

    Returns:
        Mapping of schema-qualified table name to its schema.
    """
    tables: dict[str, TableSchema] = {}
    for path in sorted(ddl_dir.glob("*.sql")):
        sql = _COMMENT.sub("", path.read_text(encoding="utf-8"))
        for match in _CREATE_TABLE.finditer(sql):
            name = match.group(1)
            body = _table_body(sql, match.end() - 1)
            tables[name] = _parse_table(name, body)
    return tables


def table_schema(table: str) -> TableSchema:
    """Schema of one DDL table.

    Args:
        table: Schema-qualified name ('bronze.github_users_raw').

    Returns:
        The parsed schema.

    Raises:
        UnknownTableError: If the table is not in schemas/ddl.
    """
    found = registry().get(table)
    if found is None:
        raise UnknownTableError(table)
    return found


def coerce(value: Json, ddl_type: DdlType) -> SinkValue:
    """Convert JSONL cell values to their DDL types, at any nesting depth.

    ISO strings become datetime/date for TIMESTAMP/DATE columns - including
    inside ARRAY, MAP values, and STRUCT fields; everything else (and VARIANT
    trees) passes through unchanged.

    Args:
        value: The parsed-JSON cell value.
        ddl_type: The column's DDL type.

    Returns:
        The coerced value.
    """
    if value is None:
        return None
    match ddl_type:
        case Scalar(kind=("timestamp" | "date") as kind) if isinstance(value, str):
            parsed = datetime.fromisoformat(value)
            return parsed if kind == "timestamp" else date.fromisoformat(value)
        case Array(element=element) if isinstance(value, list):
            return _coerce_items(value, element)
        case MapType(value=value_type) if isinstance(value, dict):
            return _coerce_mapping(value, value_type)
        case Struct(fields=fields) if isinstance(value, dict):
            return _coerce_struct(value, fields)
        case _:
            # Json is a semantic subset of SinkValue; the cast bridges the
            # container invariance the type system cannot see through.
            return cast("SinkValue", value)


def coerce_rows(table: str, rows: Sequence[Mapping[str, object]]) -> list[SinkRow]:
    """Coerce every cell of every row to its DDL type.

    Rows assembled from JSONL (or read back from the warehouse) carry ISO
    strings where the DDL declares TIMESTAMP/DATE; Parquet staging needs the
    typed values. Cells that are already typed pass through untouched, so
    this is safe to apply on any write path.

    Args:
        table: Schema-qualified table name.
        rows: Rows in DDL column shape; cells are Json or already-typed
            SinkValues (the two spellings the write paths produce).

    Returns:
        New rows with temporal values typed per the DDL.
    """
    schema = table_schema(table)
    return [
        {
            column: coerce(cast("Json", value), schema.column_type(column))
            for column, value in row.items()
        }
        for row in rows
    ]


def _coerce_items(values: Iterable[Json], element: DdlType) -> list[SinkValue]:
    return [coerce(item, element) for item in values]


def _coerce_mapping(mapping: Mapping[str, Json], value_type: DdlType) -> dict[str, SinkValue]:
    return {key: coerce(item, value_type) for key, item in mapping.items()}


def _coerce_struct(
    mapping: Mapping[str, Json], fields: tuple[tuple[str, DdlType], ...]
) -> dict[str, SinkValue]:
    field_types = dict(fields)
    return {key: coerce(item, field_types[key]) for key, item in mapping.items()}
