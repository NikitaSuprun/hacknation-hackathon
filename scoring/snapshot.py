"""Typed JSONL snapshots: the immutable inputs every scoring job is a function of.

Jobs are pure functions from (snapshot, gold inputs) to sink rows; loading the
tables happens exactly once here, and `snapshot_hash` gives rescoring its
idempotency fingerprint (same inputs, same hash, no duplicate run).
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass, fields
from datetime import UTC, datetime
from pathlib import Path

from contracts.models import Json
from scrapers.common.jsonutil import as_mapping
from tools.db import content_hash

type Row = Mapping[str, Json]
"""One table row as parsed from JSONL (read-only for the jobs)."""


class MissingFieldError(KeyError):
    """A row lacks a field the pipeline treats as mandatory."""

    def __init__(self, key: str) -> None:
        """Name the missing field."""
        super().__init__(f"row has no usable value for {key!r}")


@dataclass(frozen=True, slots=True)
class SilverSnapshot:
    """The entity-resolved silver layer (plus the SOGC filings funding needs)."""

    projects: tuple[Row, ...]
    companies: tuple[Row, ...]
    publications: tuple[Row, ...]
    contributions: tuple[Row, ...]
    authorships: tuple[Row, ...]
    officers: tuple[Row, ...]
    persons: tuple[Row, ...]
    connections: tuple[Row, ...]
    sogc: tuple[Row, ...]
    hacknation_projects: tuple[Row, ...]
    person_links: tuple[Row, ...]


@dataclass(frozen=True, slots=True)
class GoldInputs:
    """The editable/served gold rows a scoring run reads (never writes in place)."""

    theses: tuple[Row, ...]
    weights: tuple[Row, ...]
    ideals: tuple[Row, ...]
    ventures: tuple[Row, ...]
    members: tuple[Row, ...]
    scores: tuple[Row, ...]
    interviews: tuple[Row, ...]
    features: tuple[Row, ...]
    institution_scores: tuple[Row, ...]
    memos: tuple[Row, ...]
    score_runs: tuple[Row, ...]


def load_table(data_dir: Path, table: str) -> tuple[Row, ...]:
    """Read one table's JSONL file; a missing file is an empty table.

    Args:
        data_dir: Directory of `<schema>.<table>.jsonl` files.
        table: Schema-qualified table name.

    Returns:
        The parsed rows in file order.
    """
    path = data_dir / f"{table}.jsonl"
    if not path.exists():
        return ()
    lines = path.read_text(encoding="utf-8").splitlines()
    return tuple(as_mapping(json.loads(line)) for line in lines if line.strip())


def load_silver(data_dir: Path) -> SilverSnapshot:
    """Load the silver snapshot the jobs consume.

    Args:
        data_dir: Directory of JSONL files (fixtures/data or an export).

    Returns:
        The frozen snapshot.
    """
    return SilverSnapshot(
        projects=load_table(data_dir, "silver.project"),
        companies=load_table(data_dir, "silver.company"),
        publications=load_table(data_dir, "silver.publication"),
        contributions=load_table(data_dir, "silver.contribution"),
        authorships=load_table(data_dir, "silver.authorship"),
        officers=load_table(data_dir, "silver.officer"),
        persons=load_table(data_dir, "silver.person"),
        connections=load_table(data_dir, "silver.person_connection"),
        sogc=load_table(data_dir, "bronze.zefix_sogc_raw"),
        hacknation_projects=load_table(data_dir, "bronze.hacknation_projects_raw"),
        person_links=load_table(data_dir, "silver.person_source_link"),
    )


def load_gold_inputs(data_dir: Path) -> GoldInputs:
    """Load the gold-side inputs (theses, weights, prior scores, ...).

    Args:
        data_dir: Directory of JSONL files.

    Returns:
        The frozen gold inputs.
    """
    return GoldInputs(
        theses=load_table(data_dir, "gold.thesis"),
        weights=load_table(data_dir, "gold.score_weights"),
        ideals=load_table(data_dir, "gold.ideal_candidate"),
        ventures=load_table(data_dir, "gold.venture"),
        members=load_table(data_dir, "gold.venture_member"),
        scores=load_table(data_dir, "gold.venture_score"),
        interviews=load_table(data_dir, "gold.interview"),
        features=load_table(data_dir, "gold.person_features"),
        institution_scores=load_table(data_dir, "gold.institution_score"),
        memos=load_table(data_dir, "gold.memo"),
        score_runs=load_table(data_dir, "gold.score_run"),
    )


def snapshot_hash(snapshot: SilverSnapshot) -> str:
    """Content-hash the snapshot for rescore idempotency.

    Args:
        snapshot: The loaded silver snapshot.

    Returns:
        sha256 hex digest of the canonical JSON of every table.
    """
    payload = {field.name: list(getattr(snapshot, field.name)) for field in fields(snapshot)}
    return content_hash(payload)


def as_utc(text: str | None) -> datetime | None:
    """Parse an ISO date/timestamp string as a UTC-aware datetime.

    Args:
        text: The ISO string (date-only strings become midnight UTC).

    Returns:
        The aware datetime, or None for None input.
    """
    if text is None:
        return None
    parsed = datetime.fromisoformat(text)
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def get_float(row: Row, key: str) -> float | None:
    """Fetch a numeric field as float, None when absent or mistyped.

    Args:
        row: The parent row.
        key: The field name.

    Returns:
        The float value, or None (bools excluded).
    """
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def get_bool(row: Row, key: str) -> bool | None:
    """Fetch a boolean field, None when absent or mistyped.

    Args:
        row: The parent row.
        key: The field name.

    Returns:
        The boolean value, or None.
    """
    value = row.get(key)
    return value if isinstance(value, bool) else None


def require_str(row: Row, key: str) -> str:
    """Fetch a mandatory string field.

    Args:
        row: The parent row.
        key: The field name.

    Returns:
        The string value.

    Raises:
        MissingFieldError: If the field is absent or not a string.
    """
    value = row.get(key)
    if not isinstance(value, str):
        raise MissingFieldError(key)
    return value
