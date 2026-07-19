# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
# pyright: basic
"""Arrow staging for the sink: the one pyarrow seam.

Staging schemas are built from the DDL registry, so column types are explicit
and inference-free. pyright runs this file in basic mode because the pyarrow
stubs are Unknown-heavy; the public signatures stay annotated for strict-mode
importers.
"""

import io
from collections.abc import Sequence
from typing import Final

import pyarrow as pa
import pyarrow.parquet as pq

from tools.ddl_registry import Array, DdlType, MapType, Scalar, Struct, TableSchema

_SCALAR_ARROW: Final[dict[str, pa.DataType]] = {
    "string": pa.string(),
    "bigint": pa.int64(),
    "int": pa.int32(),
    "double": pa.float64(),
    "float": pa.float32(),
    "boolean": pa.bool_(),
    "timestamp": pa.timestamp("us", tz="UTC"),
    "date": pa.date32(),
    "variant": pa.string(),
}


class RowShapeError(ValueError):
    """Raised when a batch's rows do not share one column set."""

    def __init__(self, table: str) -> None:
        """Name the offending table."""
        super().__init__(f"rows for {table} do not share one column set")


def arrow_type(ddl_type: DdlType) -> pa.DataType:
    """Map a DDL type tree onto the Arrow type used for Parquet staging.

    Args:
        ddl_type: The parsed DDL type (VARIANT stages as string).

    Returns:
        The corresponding Arrow type.
    """
    match ddl_type:
        case Scalar(kind=kind):
            return _SCALAR_ARROW[kind]
        case Array(element=element):
            return pa.list_(arrow_type(element))
        case MapType(key=key, value=value):
            return pa.map_(arrow_type(key), arrow_type(value))
        case Struct(fields=fields):
            return pa.struct([(name, arrow_type(field)) for name, field in fields])


def arrow_schema(schema: TableSchema, columns: Sequence[str]) -> pa.Schema:
    """Build the staging schema for the columns present in a batch.

    Args:
        schema: The table's DDL schema.
        columns: The batch's columns, in row order.

    Returns:
        An Arrow schema with one field per present column.
    """
    return pa.schema([pa.field(c, arrow_type(schema.column_type(c))) for c in columns])


def stage_table(rows: list[dict[str, object]], schema: pa.Schema, table: str) -> pa.Table:
    """Build the Arrow table for a prepared batch against an explicit schema.

    Args:
        rows: Prepared rows sharing one column set.
        schema: The staging schema from arrow_schema().
        table: Target table, for error messages.

    Returns:
        The Arrow table.

    Raises:
        RowShapeError: If rows disagree on columns.
    """
    columns = list(rows[0].keys())
    if any(list(row.keys()) != columns for row in rows[1:]):
        raise RowShapeError(table)
    return pa.Table.from_pylist(rows, schema=schema)


def parquet_bytes(arrow_table: pa.Table) -> bytes:
    """Serialize an Arrow table to Parquet.

    Args:
        arrow_table: The staged batch.

    Returns:
        The Parquet file content.
    """
    buffer = io.BytesIO()
    pq.write_table(arrow_table, buffer)
    return buffer.getvalue()
