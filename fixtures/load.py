# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
# pyright: basic
"""Load the fixture JSONL into dealflow_dev through the shared sink (T5).

Validates first, converts temporal strings to typed values, MERGEs every
table idempotently, then proves the three contract views return persona data.
Run twice: the second pass must report 0 inserted / 0 updated everywhere.
"""

import sys
from datetime import date, datetime
from pathlib import Path
from typing import Final

from fixtures.build import DATA_DIR, LENA
from fixtures.validate import Tables, load_tables, validate
from tools.db import DatabricksSink
from tools.settings import load_databricks_settings
from tools.warehouse import Warehouse

MERGE_KEYS: Final[dict[str, list[str]]] = {
    "bronze.github_repos_raw": ["repo_id"],
    "bronze.github_users_raw": ["user_id"],
    "bronze.github_commits_raw": ["repo_id", "sha"],
    "bronze.arxiv_papers_raw": ["arxiv_id"],
    "bronze.openalex_works_raw": ["openalex_id"],
    "bronze.zefix_companies_raw": ["uid"],
    "bronze.zefix_sogc_raw": ["sogc_id"],
    "silver.person": ["person_id"],
    "silver.person_source_record": ["source_record_id"],
    "silver.person_source_link": ["link_id"],
    "silver.project": ["project_id"],
    "silver.publication": ["publication_id"],
    "silver.company": ["company_id"],
    "silver.contribution": ["contribution_id"],
    "silver.authorship": ["authorship_id"],
    "silver.officer": ["officer_id"],
    "silver.person_connection": ["person_a_id", "person_b_id", "connection_type"],
    "gold.venture": ["venture_id"],
    "gold.venture_member": ["venture_id", "person_id"],
    "gold.thesis": ["thesis_id"],
    "gold.candidate_pool": ["thesis_id", "venture_id"],
    "gold.ideal_candidate": ["profile_id"],
    "gold.institution_score": ["institution_id"],
    "gold.score_weights": ["weights_id"],
    "gold.venture_score": ["score_id"],
    "gold.person_features": ["person_id"],
    "gold.venture_gaps": ["venture_id", "field"],
    "gold.memo": ["memo_id"],
    "gold.outreach": ["outreach_id"],
    "gold.interview": ["interview_id"],
    "ops.scrape_state": ["source"],
    "ops.er_review_queue": ["review_id"],
    "ops.erasure_suppression": ["source", "source_key_hash"],
}

VARIANT_COLS: Final[dict[str, frozenset[str]]] = {
    "bronze.github_repos_raw": frozenset({"payload"}),
    "bronze.github_users_raw": frozenset({"payload"}),
    "bronze.github_commits_raw": frozenset({"payload"}),
    "bronze.arxiv_papers_raw": frozenset({"payload"}),
    "bronze.openalex_works_raw": frozenset({"payload"}),
    "bronze.zefix_companies_raw": frozenset({"payload"}),
    "bronze.zefix_sogc_raw": frozenset({"payload"}),
    "silver.person_source_link": frozenset({"evidence"}),
    "silver.project": frozenset({"structured"}),
    "silver.publication": frozenset({"source_extras"}),
    "gold.venture_member": frozenset({"evidence"}),
    "gold.ideal_candidate": frozenset({"profile_json"}),
    "gold.institution_score": frozenset({"provenance"}),
    "gold.venture_score": frozenset({"breakdown"}),
    "gold.memo": frozenset({"sections"}),
    "gold.outreach": frozenset({"question_plan"}),
    "gold.interview": frozenset({"transcript", "extracted"}),
    "ops.scrape_state": frozenset({"cursor"}),
    "ops.er_review_queue": frozenset({"features"}),
}

# Columns whose DDL type is DATE; everything else ending in _at is TIMESTAMP.
DATE_COLS: Final[dict[str, frozenset[str]]] = {
    "bronze.zefix_sogc_raw": frozenset({"published_date"}),
    "silver.publication": frozenset({"published_at"}),
    "silver.company": frozenset({"incorporation_date"}),
    "silver.officer": frozenset({"registered_at", "deregistered_at"}),
    "silver.person_connection": frozenset({"first_seen", "last_seen"}),
}

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
        "SELECT signal_type, artifact_name FROM dealflow_dev.gold.v_person_signals "  # noqa: S608 - constant fixture id, no user input
        f"WHERE person_id = '{LENA}' ORDER BY signal_type",
    ),
)


def _typed_value(table: str, column: str, value: object) -> object:
    if not isinstance(value, str):
        return value
    if column in DATE_COLS.get(table, frozenset()):
        return date.fromisoformat(value)
    if column.endswith("_at"):
        return datetime.fromisoformat(value)
    return value


def typed_rows(table: str, rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """Convert ISO temporal strings into typed values for Parquet staging.

    Args:
        table: Schema-qualified table name.
        rows: Rows as parsed from JSONL.

    Returns:
        New rows with dates and timestamps as Python objects.
    """
    return [
        {column: _typed_value(table, column, value) for column, value in row.items()}
        for row in rows
    ]


def load_all(tables: Tables, sink: DatabricksSink) -> tuple[int, int]:
    """MERGE every fixture table into the sink's catalog.

    Args:
        tables: Parsed fixture tables.
        sink: The shared Databricks sink.

    Returns:
        Total (inserted, updated) across all tables.
    """
    inserted = 0
    updated = 0
    for table in sorted(tables):
        result = sink.upsert(
            table,
            typed_rows(table, tables[table]),
            MERGE_KEYS[table],
            variant_cols=VARIANT_COLS.get(table, frozenset()),
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
