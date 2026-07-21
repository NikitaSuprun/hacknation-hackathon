"""T12: the right-to-erasure script (`python -m tools.erase_person`).

plan_erasure is pure: given the person's rows per table it returns a plan -
DELETE operations across bronze/silver/gold/ops, a person tombstone, the
audit row for ops.erasure_log, and ops.erasure_suppression entries keyed by
sha256(source_key) so a re-scrape can never resurrect the identity. execute()
applies a plan through a SqlRunner and the shared sink. SQL here interpolates
only identifier-guarded names and escaped literals (the S608 ignore's basis).
"""

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

import typer

from contracts.interfaces import Sink
from contracts.models import Json, SinkRow
from er.io import RowSource, sink_all
from scrapers.common.jsonutil import get_str
from scrapers.common.state import SqlRunner, require_identifier

app: Final[typer.Typer] = typer.Typer(add_completion=False)

Row = dict[str, Json]

_FACT_TABLES: Final[tuple[str, ...]] = (
    "silver.contribution",
    "silver.authorship",
    "silver.officer",
)


class UnknownPersonError(LookupError):
    """Raised when the person row is absent from the provided tables."""

    def __init__(self, person_id: str) -> None:
        """Name the missing person."""
        super().__init__(f"person {person_id} not found in silver.person rows")


@dataclass(frozen=True, slots=True)
class DeleteOp:
    """One DELETE against a table, as data."""

    table: str
    where: str


@dataclass(frozen=True, slots=True)
class ErasurePlan:
    """Everything an erasure implies; execute() applies it."""

    person_id: str
    erasure_id: str
    deletes: tuple[DeleteOp, ...]
    upserts: Mapping[str, list[SinkRow]]


def source_key_hash(source_key: str) -> str:
    """The suppression hash of one source key (sha256 hex).

    Args:
        source_key: The per-source key.

    Returns:
        The hex digest stored in ops.erasure_suppression.
    """
    return hashlib.sha256(source_key.encode("utf-8")).hexdigest()


def _escape(value: str) -> str:
    return value.replace("'", "''")


def _in_clause(column: str, values: Sequence[str]) -> str:
    quoted = ", ".join(f"'{_escape(value)}'" for value in sorted(values))
    return f"{column} IN ({quoted})"


def _person_links(tables: Mapping[str, list[Row]], person_id: str) -> list[Row]:
    return [
        row
        for row in tables.get("silver.person_source_link", [])
        if row.get("person_id") == person_id
    ]


def _person_psrs(tables: Mapping[str, list[Row]], psr_ids: frozenset[str]) -> list[Row]:
    return [
        row
        for row in tables.get("silver.person_source_record", [])
        if str(row.get("source_record_id")) in psr_ids
    ]


def _source_keys(psrs: Sequence[Row], source: str) -> list[str]:
    return [
        key
        for row in psrs
        if row.get("source") == source and (key := get_str(row, "source_key")) is not None
    ]


def _bronze_deletes(psrs: Sequence[Row]) -> list[DeleteOp]:
    ops: list[DeleteOp] = []
    github_ids = _source_keys(psrs, "github")
    if github_ids:
        numeric = ", ".join(str(int(key)) for key in sorted(github_ids))
        ops.append(DeleteOp(table="bronze.github_users_raw", where=f"user_id IN ({numeric})"))
        ops.append(
            DeleteOp(table="bronze.github_commits_raw", where=f"author_user_id IN ({numeric})")
        )
    hacknation_ids = _source_keys(psrs, "hacknation")
    if hacknation_ids:
        ops.append(
            DeleteOp(
                table="bronze.hacknation_people_raw",
                where=_in_clause("user_id", hacknation_ids),
            )
        )
    return ops


def _tombstone(person_row: Row, now: datetime) -> SinkRow:
    """Strip every PII column; only the id, status, and timestamps survive."""
    created = get_str(person_row, "created_at")
    return {
        "person_id": str(person_row.get("person_id")),
        "full_name": None,
        "display_name": None,
        "primary_email": None,
        "emails": [],
        "github_login": None,
        "orcid": None,
        "website_url": None,
        "linkedin_url": None,
        "cv_url": None,
        "twitter_handle": None,
        "affiliation": None,
        "location": None,
        "country_code": None,
        "headline": None,
        "avatar_url": None,
        "data_quality_score": None,
        "status": "erased",
        "merged_into_person_id": None,
        "created_at": datetime.fromisoformat(created) if created is not None else now,
        "updated_at": now,
    }


def plan_erasure(  # noqa: PLR0913 - the erasure decision surface, injected for testability
    person_id: str,
    tables: Mapping[str, list[Row]],
    *,
    scope: str,
    clock: Callable[[], datetime],
    actor: str,
    erasure_id: str,
) -> ErasurePlan:
    """Plan the full erasure of one person.

    Args:
        person_id: The golden person to erase.
        tables: The person-relevant rows per schema-qualified table.
        scope: Recorded erasure scope (e.g. 'full').
        clock: Injected time source.
        actor: Recorded executor.
        erasure_id: The audit-row id (injected for deterministic tests).

    Returns:
        The plan.

    Raises:
        UnknownPersonError: If silver.person holds no row for the person.
    """
    person_row = next(
        (row for row in tables.get("silver.person", []) if row.get("person_id") == person_id),
        None,
    )
    if person_row is None:
        raise UnknownPersonError(person_id)
    now = clock()
    links = _person_links(tables, person_id)
    psr_ids = frozenset(
        key for row in links if (key := get_str(row, "source_record_id")) is not None
    )
    psrs = _person_psrs(tables, psr_ids)
    deletes = _deletes(person_id, psr_ids, psrs)
    suppression: list[SinkRow] = [
        {
            "source": str(row.get("source")),
            "source_key_hash": source_key_hash(str(row.get("source_key"))),
            "created_at": now,
        }
        for row in sorted(psrs, key=lambda item: str(item.get("source_record_id")))
    ]
    cv_url = get_str(person_row, "cv_url")
    erasure_log: SinkRow = {
        "erasure_id": erasure_id,
        "person_id": person_id,
        "requested_at": now,
        "requester_hash": None,
        "scope": scope,
        "executed_at": now,
        "executed_by": actor,
        "rows_deleted": {
            op.table: _row_count(tables, op.table, psr_ids, person_id) for op in deletes
        },
        "vacuum_after": None,
        # The CV file lives in a UC Volume, not a table; the pointer purge is
        # recorded here so the DPO runbook removes the file alongside the rows.
        "notes": f"purge CV file from UC Volume: {cv_url}" if cv_url is not None else None,
    }
    upserts: dict[str, list[SinkRow]] = {
        "silver.person": [_tombstone(person_row, now)],
        "ops.erasure_log": [erasure_log],
        "ops.erasure_suppression": suppression,
    }
    return ErasurePlan(
        person_id=person_id, erasure_id=erasure_id, deletes=tuple(deletes), upserts=upserts
    )


def _deletes(person_id: str, psr_ids: frozenset[str], psrs: Sequence[Row]) -> list[DeleteOp]:
    person_clause = f"person_id = '{_escape(person_id)}'"
    ops: list[DeleteOp] = list(_bronze_deletes(psrs))
    if psr_ids:
        psr_clause = _in_clause("source_record_id", sorted(psr_ids))
        ops.append(DeleteOp(table="silver.person_source_record", where=psr_clause))
        ops.append(DeleteOp(table="silver.person_source_link", where=psr_clause))
        ops.extend(DeleteOp(table=table, where=psr_clause) for table in _FACT_TABLES)
        ops.append(
            DeleteOp(
                table="ops.er_review_queue",
                where=f"{psr_clause} OR candidate_person_id = '{_escape(person_id)}'",
            )
        )
    ops.append(
        DeleteOp(
            table="silver.person_connection",
            where=f"person_a_id = '{_escape(person_id)}' OR person_b_id = '{_escape(person_id)}'",
        )
    )
    ops.append(DeleteOp(table="gold.person_features", where=person_clause))
    ops.append(DeleteOp(table="gold.venture_member", where=person_clause))
    return ops


def _row_count(
    tables: Mapping[str, list[Row]], table: str, psr_ids: frozenset[str], person_id: str
) -> int:
    rows = tables.get(table, [])
    if table.startswith("bronze."):
        return len(rows)
    return sum(
        1
        for row in rows
        if str(row.get("source_record_id")) in psr_ids
        or row.get("person_id") == person_id
        or row.get("person_a_id") == person_id
        or row.get("person_b_id") == person_id
        or row.get("candidate_person_id") == person_id
    )


def execute(plan: ErasurePlan, runner: SqlRunner, sink: Sink, *, catalog: str) -> None:
    """Apply one erasure plan.

    Args:
        plan: The planned erasure.
        runner: SQL surface for the DELETE statements.
        sink: The shared sink for tombstone/log/suppression upserts.
        catalog: Target catalog (identifier-guarded).
    """
    safe_catalog = require_identifier(catalog)
    for op in plan.deletes:
        table = require_identifier(op.table)
        runner.execute(f"DELETE FROM {safe_catalog}.{table} WHERE {op.where}")
    sink_all(sink, plan.upserts)


def _load_person_tables(source: RowSource) -> dict[str, list[Row]]:
    tables = (
        "silver.person",
        "silver.person_source_link",
        "silver.person_source_record",
        "silver.contribution",
        "silver.authorship",
        "silver.officer",
        "silver.person_connection",
        "gold.person_features",
        "gold.venture_member",
        "ops.er_review_queue",
        "bronze.github_users_raw",
        "bronze.github_commits_raw",
        "bronze.hacknation_people_raw",
    )
    return {table: source.rows(table) for table in tables}


@app.command()
def main(  # pyright: ignore[reportUnusedFunction] - typer registers the command via the decorator
    person_id: str,
    *,
    scope: str = "full",
    actor: str = "dpo",
    dry_run: bool = False,
    catalog: str = "dealflow_dev",
) -> None:
    """Erase one person across all four schemas and block re-scrapes."""
    from datetime import UTC  # noqa: PLC0415 - tiny local import

    from er.io import WarehouseRowSource  # noqa: PLC0415 - live-only import
    from tools import ids  # noqa: PLC0415 - id mint for the audit row
    from tools.db import DatabricksSink  # noqa: PLC0415 - live-only import
    from tools.settings import load_databricks_settings  # noqa: PLC0415 - live-only import
    from tools.warehouse import Warehouse  # noqa: PLC0415 - live-only import

    settings = load_databricks_settings()
    warehouse = Warehouse(settings)
    source = WarehouseRowSource(warehouse, catalog)
    plan = plan_erasure(
        person_id,
        _load_person_tables(source),
        scope=scope,
        clock=lambda: datetime.now(UTC),
        actor=actor,
        erasure_id=ids.new_random_id(),
    )
    if dry_run:
        typer.echo(json.dumps({"deletes": [op.table for op in plan.deletes]}, sort_keys=True))
        return
    execute(plan, warehouse, DatabricksSink(settings, catalog), catalog=catalog)
    typer.echo(f"erased {person_id}: {len(plan.deletes)} delete ops")


if __name__ == "__main__":
    app()
