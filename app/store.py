# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""The one data seam of the app: fixture-backed or warehouse-backed rows.

FixtureStore serves fixtures/data JSONL with an in-memory overlay so the demo
flows (outreach, interview, rescore) mutate state without touching the golden
files; the gold.v_* view contract is composed in Python from the base tables.
WarehouseStore reads the same names live via to_json(struct(*)) selects and
writes through the shared merge-upsert sink.
"""

import json
from datetime import date, datetime
from pathlib import Path
from typing import Final, Protocol

from app.queries import select_rows_sql
from contracts.interfaces import Sink
from contracts.models import Json, SinkRow, SinkValue
from scoring.snapshot import load_table
from scrapers.common.jsonutil import as_mapping
from scrapers.common.state import SqlRunner, require_identifier
from tools.db import canonical_json
from tools.ddl_registry import table_schema

VIEW_RANKED_VENTURES: Final[str] = "gold.v_ranked_ventures"
VIEW_VENTURE_TEAM: Final[str] = "gold.v_venture_team"

RANKED_SCORE_COLUMNS: Final[tuple[str, ...]] = (
    "final_score",
    "confidence",
    "ideal_match",
    "s_individual_experience",
    "s_schools",
    "s_network_ties",
    "s_prior_collaboration",
    "s_problem_realness",
    "s_product_defensibility",
    "s_market",
    "s_traction",
    "breakdown",
    "scored_at",
)
TEAM_PERSON_COLUMNS: Final[tuple[str, ...]] = (
    "person_id",
    "full_name",
    "headline",
    "github_login",
    "orcid",
    "linkedin_url",
    "affiliation",
    "avatar_url",
)
TEAM_MEMBER_COLUMNS: Final[tuple[str, ...]] = (
    "role_hint",
    "is_founder_guess",
    "weight",
    "evidence",
)


class ViewNotWritableError(ValueError):
    """An upsert targeted a view instead of a base table."""

    def __init__(self, name: str) -> None:
        """Name the rejected target."""
        super().__init__(f"{name} is a view; writes must target base tables")


class DataStore(Protocol):
    """Rows in, rows out: the whole persistence surface the app needs."""

    def rows(self, name: str) -> list[dict[str, Json]]:
        """Return every row of a table or gold view as parsed JSON."""
        ...

    def upsert(self, table: str, rows: list[SinkRow]) -> None:
        """Idempotently merge rows into a base table on its primary key."""
        ...


def to_json_value(value: SinkValue) -> Json:
    """Render one sink cell as plain JSON (temporals become ISO strings).

    Args:
        value: The sink cell.

    Returns:
        The JSON-shaped value.
    """
    match value:
        case datetime() | date():
            return value.isoformat()
        case list():
            return [to_json_value(item) for item in value]
        case dict():
            return {key: to_json_value(item) for key, item in value.items()}
        case _:
            return value


def _row_key(row: dict[str, Json], keys: tuple[str, ...]) -> tuple[str, ...]:
    if not keys:
        return (canonical_json(row),)
    return tuple(str(row.get(key)) for key in keys)


class FixtureStore:
    """JSONL-backed store with a write overlay; zero credentials required."""

    def __init__(self, data_dir: Path) -> None:
        """Bind the fixture directory; the overlay starts empty."""
        self._data_dir: Final[Path] = data_dir
        self._base: Final[dict[str, list[dict[str, Json]]]] = {}
        self._overlay: Final[dict[str, dict[tuple[str, ...], dict[str, Json]]]] = {}

    def rows(self, name: str) -> list[dict[str, Json]]:
        """Return the merged base+overlay rows, composing gold views in Python.

        Args:
            name: Schema-qualified table or supported gold view.

        Returns:
            The rows; overlay versions win over fixture rows.
        """
        if name == VIEW_RANKED_VENTURES:
            return self._ranked_ventures()
        if name == VIEW_VENTURE_TEAM:
            return self._venture_team()
        return self._table_rows(name)

    def upsert(self, table: str, rows: list[SinkRow]) -> None:
        """Merge rows into the in-memory overlay on the table's primary key.

        Args:
            table: Schema-qualified base table.
            rows: Rows in DDL column shape (temporals allowed).

        Raises:
            ViewNotWritableError: If the target is a gold view.
        """
        if table in {VIEW_RANKED_VENTURES, VIEW_VENTURE_TEAM}:
            raise ViewNotWritableError(table)
        keys = table_schema(table).primary_key
        bucket = self._overlay.setdefault(table, {})
        for row in rows:
            plain = {column: to_json_value(value) for column, value in row.items()}
            bucket[_row_key(plain, keys)] = plain

    def _table_rows(self, table: str) -> list[dict[str, Json]]:
        keys = table_schema(table).primary_key
        if table not in self._base:
            self._base[table] = [dict(row) for row in load_table(self._data_dir, table)]
        overlay = self._overlay.get(table, {})
        merged: list[dict[str, Json]] = []
        seen: set[tuple[str, ...]] = set()
        for row in self._base[table]:
            key = _row_key(row, keys)
            seen.add(key)
            merged.append(dict(overlay.get(key, row)))
        merged.extend(dict(row) for key, row in overlay.items() if key not in seen)
        return merged

    def _latest_scores(self) -> dict[str, dict[str, Json]]:
        latest: dict[str, dict[str, Json]] = {}
        for row in self._table_rows("gold.venture_score"):
            venture_id = row.get("venture_id")
            if row.get("is_latest") is True and isinstance(venture_id, str):
                latest[venture_id] = row
        return latest

    def _ranked_ventures(self) -> list[dict[str, Json]]:
        scores = self._latest_scores()
        ranked: list[dict[str, Json]] = []
        for venture in self._table_rows("gold.venture"):
            venture_id = venture.get("venture_id")
            score = scores.get(venture_id) if isinstance(venture_id, str) else None
            row: dict[str, Json] = {
                "venture_id": venture_id,
                "name": venture.get("name"),
                "one_liner": venture.get("one_liner"),
                "status": venture.get("status"),
                "quality_tier": venture.get("quality_tier"),
                "market_tags": venture.get("market_tags"),
            }
            for column in RANKED_SCORE_COLUMNS:
                row[column] = score.get(column) if score is not None else None
            ranked.append(row)
        return ranked

    def _active_persons(self) -> dict[str, dict[str, Json]]:
        persons: dict[str, dict[str, Json]] = {}
        for row in self._table_rows("silver.person"):
            person_id = row.get("person_id")
            if row.get("status") == "active" and isinstance(person_id, str):
                persons[person_id] = row
        return persons

    def _venture_team(self) -> list[dict[str, Json]]:
        persons = self._active_persons()
        team: list[dict[str, Json]] = []
        for member in self._table_rows("gold.venture_member"):
            person_id = member.get("person_id")
            person = persons.get(person_id) if isinstance(person_id, str) else None
            if person is None:
                continue
            row: dict[str, Json] = {"venture_id": member.get("venture_id")}
            row.update({column: person.get(column) for column in TEAM_PERSON_COLUMNS})
            row.update({column: member.get(column) for column in TEAM_MEMBER_COLUMNS})
            team.append(row)
        return team


class WarehouseStore:
    """Live store: allowlisted JSON selects for reads, merge upserts for writes."""

    def __init__(self, runner: SqlRunner, sink: Sink, catalog: str) -> None:
        """Bind the query runner, the merge sink, and one guarded catalog."""
        self._runner: Final[SqlRunner] = runner
        self._sink: Final[Sink] = sink
        self._catalog: Final[str] = require_identifier(catalog)

    def rows(self, name: str) -> list[dict[str, Json]]:
        """SELECT every row of the table or view as parsed JSON.

        Args:
            name: Schema-qualified table or view from the read allowlist.

        Returns:
            The parsed rows.
        """
        fetched = self._runner.execute(select_rows_sql(self._catalog, name))
        return [as_mapping(json.loads(str(cells[0]))) for cells in fetched if cells[0] is not None]

    def upsert(self, table: str, rows: list[SinkRow]) -> None:
        """MERGE rows through the shared sink with registry-driven keys.

        Args:
            table: Schema-qualified base table.
            rows: Rows in DDL column shape.
        """
        schema = table_schema(table)
        self._sink.upsert(table, rows, list(schema.primary_key), variant_cols=schema.variant_cols)
