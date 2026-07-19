# Copyright (c) 2026 Venture Hunt. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Idempotent lakehouse writes: canonical JSON, Parquet to a UC Volume, one MERGE.

The connector's native parameters cap at ~25 rows per statement, so batches are
staged as Parquet and merged in one statement. VARIANT columns travel as
canonical-JSON strings and are rebuilt with parse_json() in the source SELECT.
Erasure suppression is enforced inside the MERGE source, so a re-scrape can
never resurrect an erased identity.
"""

import contextlib
import hashlib
import io
import json
import re
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final

from databricks.sdk import WorkspaceClient
from databricks.sdk.errors.base import DatabricksError

from contracts.models import SinkRow, UpsertResult
from tools._arrow import RowShapeError, arrow_schema, parquet_bytes, stage_table
from tools.ddl_registry import table_schema
from tools.settings import DatabricksSettings
from tools.warehouse import Warehouse

__all__ = [
    "SUPPRESSION_RULES",
    "DatabricksSink",
    "MergeSpec",
    "RowShapeError",
    "SuppressionRule",
    "UnsafeIdentifierError",
    "build_merge_sql",
    "build_suppressed_count_sql",
    "canonical_json",
    "content_hash",
    "parquet_bytes",
    "prepare_rows",
    "stage_table",
]

_IDENTIFIER: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9_.]+$")


class UnsafeIdentifierError(ValueError):
    """Raised when a table or column name is not a plain SQL identifier."""

    def __init__(self, name: str) -> None:
        """Quote the offending name."""
        super().__init__(f"not a safe SQL identifier: {name!r}")


def _require_identifiers(names: Iterable[str]) -> None:
    """Reject any name that could not have come from the DDL contract."""
    for name in names:
        if _IDENTIFIER.fullmatch(name) is None:
            raise UnsafeIdentifierError(name)


@dataclass(frozen=True, slots=True)
class SuppressionRule:
    """How a table's rows map onto ops.erasure_suppression keys."""

    source: str | None
    source_col: str | None
    key_col: str


# Person-bearing MERGE targets; artifact tables need no guard.
SUPPRESSION_RULES: Final[dict[str, SuppressionRule]] = {
    "bronze.github_users_raw": SuppressionRule("github", None, "user_id"),
    "bronze.hacknation_cvs_raw": SuppressionRule("hacknation", None, "user_id"),
    "bronze.hacknation_people_raw": SuppressionRule("hacknation", None, "user_id"),
    "silver.person_source_record": SuppressionRule(None, "source", "source_key"),
}


def canonical_json(value: object) -> str:
    """Render a JSON value canonically: sorted keys, compact separators.

    Args:
        value: Any JSON-serializable value.

    Returns:
        The canonical rendering (the content-hash input).
    """
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def content_hash(payload: object) -> str:
    """The change-detection hash every raw payload column carries.

    Args:
        payload: The raw payload value.

    Returns:
        sha256 hex digest of the canonical JSON.
    """
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def prepare_rows(rows: list[SinkRow], variant_cols: frozenset[str]) -> list[SinkRow]:
    """Encode VARIANT columns as canonical-JSON strings for Parquet staging.

    Args:
        rows: Rows in DDL column shape.
        variant_cols: Columns whose target type is VARIANT.

    Returns:
        New rows with variant values stringified (None passes through).
    """
    prepared: list[SinkRow] = []
    for row in rows:
        encoded = dict(row)
        for column in variant_cols:
            value = encoded.get(column)
            if value is not None:
                encoded[column] = canonical_json(value)
        prepared.append(encoded)
    return prepared


def _suppression_predicate(catalog: str, rule: SuppressionRule, alias: str) -> str:
    source_expr = f"'{rule.source}'" if rule.source is not None else f"{alias}.{rule.source_col}"
    return (
        f"NOT EXISTS (SELECT 1 FROM {catalog}.ops.erasure_suppression es "
        f"WHERE es.source = {source_expr} "
        f"AND es.source_key_hash = sha2(CAST({alias}.{rule.key_col} AS STRING), 256))"
    )


def _change_predicate(
    columns: list[str],
    keys: list[str],
    variant_cols: frozenset[str],
    complex_cols: frozenset[str],
    hash_col: str,
) -> str:
    if hash_col in columns:
        return f"t.{hash_col} <> s.{hash_col}"
    comparisons: list[str] = []
    for column in columns:
        if column in keys:
            continue
        if column in variant_cols or column in complex_cols:
            comparisons.append(f"to_json(t.{column}) <=> to_json(s.{column})")
        else:
            comparisons.append(f"t.{column} <=> s.{column}")
    return "NOT (" + " AND ".join(comparisons) + ")"


@dataclass(frozen=True, slots=True)
class MergeSpec:
    """Everything the MERGE generator needs for one staged batch."""

    catalog: str
    table: str
    columns: list[str]
    keys: list[str]
    staged_path: str
    variant_cols: frozenset[str]
    complex_cols: frozenset[str]
    hash_col: str


def build_merge_sql(spec: MergeSpec) -> str:
    """Generate the idempotent MERGE statement for one staged batch.

    Args:
        spec: Table, columns, keys, staged path, and column categories.

    Returns:
        The MERGE statement.
    """
    projection = ", ".join(
        f"parse_json(src.{c}) AS {c}" if c in spec.variant_cols else f"src.{c}"
        for c in spec.columns
    )
    rule = SUPPRESSION_RULES.get(spec.table)
    where = f" WHERE {_suppression_predicate(spec.catalog, rule, 'src')}" if rule else ""
    on = " AND ".join(f"t.{k} = s.{k}" for k in spec.keys)
    changed = _change_predicate(
        spec.columns, spec.keys, spec.variant_cols, spec.complex_cols, spec.hash_col
    )
    updates = ", ".join(f"t.{c} = s.{c}" for c in spec.columns if c not in spec.keys)
    inserts = ", ".join(spec.columns)
    values = ", ".join(f"s.{c}" for c in spec.columns)
    return (
        f"MERGE INTO {spec.catalog}.{spec.table} t\n"
        f"USING (SELECT {projection} FROM parquet.`{spec.staged_path}` src{where}) s\n"
        f"ON {on}\n"
        f"WHEN MATCHED AND ({changed}) THEN UPDATE SET {updates}\n"
        f"WHEN NOT MATCHED THEN INSERT ({inserts}) VALUES ({values})"
    )


def build_suppressed_count_sql(catalog: str, staged_path: str, rule: SuppressionRule) -> str:
    """Count staged rows the suppression guard will block.

    Args:
        catalog: Target catalog.
        staged_path: UC Volume path of the staged Parquet file.
        rule: The table's suppression rule.

    Returns:
        A COUNT statement over the staged file.
    """
    predicate = _suppression_predicate(catalog, rule, "src")
    return f"SELECT count(*) FROM parquet.`{staged_path}` src WHERE NOT ({predicate})"


def _as_int(value: object) -> int:
    return int(str(value))


class DatabricksSink:
    """The Sink implementation: Parquet to ops.staging, then one MERGE."""

    _settings: Final[DatabricksSettings]
    _catalog: Final[str]
    _warehouse: Final[Warehouse]

    def __init__(self, settings: DatabricksSettings, catalog: str = "dealflow_dev") -> None:
        """Bind to one catalog; connections are opened per upsert."""
        self._settings = settings
        self._catalog = catalog
        self._warehouse = Warehouse(settings)

    def _workspace(self) -> WorkspaceClient:
        return WorkspaceClient(
            host=self._settings.host,
            client_id=self._settings.client_id,
            client_secret=self._settings.client_secret,
        )

    def _staged_path(self, table: str) -> str:
        run_id = uuid.uuid4().hex
        safe_table = table.replace(".", "_")
        return f"/Volumes/{self._catalog}/ops/staging/{safe_table}/{run_id}.parquet"

    def _upload(self, path: str, content: bytes) -> None:
        self._workspace().files.upload(path, io.BytesIO(content), overwrite=True)

    def _cleanup(self, path: str) -> None:
        # Staging leftovers are harmless; never fail a completed merge over cleanup.
        with contextlib.suppress(DatabricksError):
            self._workspace().files.delete(path)

    def _run_merge(
        self, merge_sql: str, count_sql: str | None, staged: int, table: str
    ) -> UpsertResult:
        with self._warehouse.cursor() as cursor:
            suppressed = 0
            if count_sql is not None:
                cursor.execute(count_sql)
                suppressed = _as_int(cursor.fetchall()[0][0])
            cursor.execute(merge_sql)
            metrics = cursor.fetchall()[0]
        updated = _as_int(metrics[1])
        inserted = _as_int(metrics[3])
        return UpsertResult(
            table=table,
            inserted=inserted,
            updated=updated,
            skipped_unchanged=staged - suppressed - inserted - updated,
            suppressed=suppressed,
        )

    def upsert(
        self,
        table: str,
        rows: list[SinkRow],
        keys: list[str],
        *,
        variant_cols: frozenset[str] = frozenset(),
        hash_col: str = "content_hash",
    ) -> UpsertResult:
        """Idempotently MERGE rows on keys, skipping unchanged content.

        Args:
            table: Schema-qualified target ('bronze.github_users_raw').
            rows: Rows in DDL column shape.
            keys: Merge key columns.
            variant_cols: Columns whose target type is VARIANT.
            hash_col: Change-detection column; when the rows lack it the
                whole row is compared instead.

        Returns:
            Merge counts, including rows blocked by erasure suppression.
        """
        if not rows:
            return UpsertResult(
                table=table, inserted=0, updated=0, skipped_unchanged=0, suppressed=0
            )
        schema = table_schema(table)
        prepared = prepare_rows(rows, variant_cols)
        columns = list(prepared[0].keys())
        _require_identifiers([table, *keys, *columns])
        arrow_table = stage_table(prepared, arrow_schema(schema, columns), table)
        staged_path = self._staged_path(table)
        merge_sql = build_merge_sql(
            MergeSpec(
                catalog=self._catalog,
                table=table,
                columns=columns,
                keys=keys,
                staged_path=staged_path,
                variant_cols=variant_cols,
                complex_cols=schema.complex_cols,
                hash_col=hash_col,
            )
        )
        rule = SUPPRESSION_RULES.get(table)
        count_sql = build_suppressed_count_sql(self._catalog, staged_path, rule) if rule else None
        self._upload(staged_path, parquet_bytes(arrow_table))
        try:
            return self._run_merge(merge_sql, count_sql, len(rows), table)
        finally:
            self._cleanup(staged_path)
