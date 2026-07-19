# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
# pyright: basic
"""Arrow staging for the sink: the one dynamically-typed seam.

Batches arrive as plain dict rows, so element types are only known at runtime;
pyright runs this file in basic mode instead of scattering suppressions. The
public signatures stay fully annotated for strict-mode importers.
"""

import io

import pyarrow as pa
import pyarrow.parquet as pq


class RowShapeError(ValueError):
    """Raised when a batch's rows do not share one column set."""

    def __init__(self, table: str) -> None:
        """Name the offending table."""
        super().__init__(f"rows for {table} do not share one column set")


def _map_value_type(values: list[dict[str, object]]) -> pa.DataType:
    flat = [v for mapping in values for v in mapping.values()]
    if all(isinstance(v, int) for v in flat):
        return pa.int64()
    if all(isinstance(v, int | float) for v in flat):
        return pa.float64()
    return pa.string()


def _column_array(values: list[object]) -> pa.Array:
    dicts = [v for v in values if isinstance(v, dict)]
    if dicts:
        mappings = [{str(k): v for k, v in d.items()} for d in dicts]
        map_type = pa.map_(pa.string(), _map_value_type(mappings))
        return pa.array(values, type=map_type)  # pyright: ignore[reportCallIssue, reportArgumentType] - dynamic row values; the overload resolves at runtime
    return pa.array(values)  # pyright: ignore[reportCallIssue, reportArgumentType] - dynamic row values; the overload resolves at runtime


def stage_table(rows: list[dict[str, object]], table: str) -> tuple[pa.Table, list[str]]:
    """Build the Arrow table for a prepared batch.

    Args:
        rows: Prepared rows sharing one column set.
        table: Target table, for error messages.

    Returns:
        The Arrow table and the column order.

    Raises:
        RowShapeError: If rows disagree on columns.
    """
    columns = list(rows[0].keys())
    if any(list(row.keys()) != columns for row in rows[1:]):
        raise RowShapeError(table)
    arrays = [_column_array([row[c] for row in rows]) for c in columns]
    return pa.Table.from_arrays(arrays, names=columns), columns


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
