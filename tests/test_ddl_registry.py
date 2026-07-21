"""The DDL registry is the single source of truth for tables, types, and keys."""

from datetime import UTC, date, datetime
from typing import Final

from contracts.models import Json
from fixtures.build import DATA_DIR
from fixtures.validate import load_tables
from tools._arrow import arrow_schema
from tools.ddl_registry import (
    Array,
    Scalar,
    Struct,
    coerce,
    coerce_rows,
    parse_type,
    registry,
    table_schema,
)

# Golden primary keys: drift here means the DDL contract itself moved.
_EXPECTED_KEYS: Final[dict[str, tuple[str, ...]]] = {
    "bronze.github_repos_raw": ("repo_id",),
    "bronze.github_users_raw": ("user_id",),
    "bronze.github_commits_raw": ("repo_id", "sha"),
    "bronze.arxiv_papers_raw": ("arxiv_id",),
    "bronze.openalex_works_raw": ("openalex_id",),
    "bronze.s2_papers_raw": ("s2_id",),
    "bronze.paper_code_links": ("repo_url", "paper_arxiv_id"),
    "bronze.zefix_companies_raw": ("uid",),
    "bronze.zefix_sogc_raw": ("sogc_id",),
    "bronze.hacknation_people_raw": ("user_id",),
    "bronze.hacknation_projects_raw": ("project_id",),
    "bronze.hacknation_cvs_raw": ("user_id",),
    "silver.person": ("person_id",),
    "silver.person_source_record": ("source_record_id",),
    "silver.person_source_link": ("link_id",),
    "silver.project": ("project_id",),
    "silver.publication": ("publication_id",),
    "silver.company": ("company_id",),
    "silver.contribution": ("contribution_id",),
    "silver.authorship": ("authorship_id",),
    "silver.officer": ("officer_id",),
    "silver.person_connection": ("person_a_id", "person_b_id", "connection_type"),
    "gold.venture": ("venture_id",),
    "gold.venture_member": ("venture_id", "person_id"),
    "gold.thesis": ("thesis_id",),
    "gold.candidate_pool": ("thesis_id", "venture_id"),
    "gold.ideal_candidate": ("profile_id",),
    "gold.institution_score": ("institution_id",),
    "gold.score_weights": ("weights_id",),
    "gold.venture_score": ("score_id",),
    "gold.person_features": ("person_id",),
    "gold.venture_gaps": ("venture_id", "field"),
    "gold.memo": ("memo_id",),
    "gold.outreach": ("outreach_id",),
    "gold.interview": ("interview_id",),
    "gold.score_run": ("run_id",),
    "ops.scrape_state": ("source",),
    "ops.er_review_queue": ("review_id",),
    "ops.llm_adjudications": ("pair_id",),
    "ops.llm_run_log": (),
    "ops.data_quality_report": (),
    "ops.erasure_log": ("erasure_id",),
    "ops.erasure_suppression": ("source", "source_key_hash"),
    "bronze._rejects": (),
}


def test_registry_covers_every_ddl_table_with_expected_keys() -> None:
    parsed = registry()
    assert set(parsed) == set(_EXPECTED_KEYS)
    for table, keys in _EXPECTED_KEYS.items():
        assert parsed[table].primary_key == keys, table


def test_fixture_columns_exactly_match_ddl() -> None:
    # JSONL serializes with sorted keys, so compare sets: no missing, no extra.
    for table, rows in load_tables(DATA_DIR).items():
        schema = table_schema(table)
        for row in rows:
            assert set(row.keys()) == set(schema.column_names), table


def test_outreach_history_parses_as_struct_array() -> None:
    history = table_schema("gold.outreach").column_type("history")
    assert history == Array(
        element=Struct(
            fields=(
                ("state", Scalar(kind="string")),
                ("ts", Scalar(kind="timestamp")),
                ("actor", Scalar(kind="string")),
            )
        )
    )


def test_variant_and_complex_classification() -> None:
    interview = table_schema("gold.interview")
    assert interview.variant_cols == {"transcript", "extracted"}
    project = table_schema("silver.project")
    assert "structured" in project.variant_cols
    assert {"market_tags", "languages", "topics"} <= project.complex_cols
    assert "structured" not in project.complex_cols


def test_arrow_schema_builds_for_every_table() -> None:
    for table, schema in registry().items():
        built = arrow_schema(schema, list(schema.column_names))
        assert len(built) == len(schema.columns), table
    languages = str(arrow_schema(table_schema("silver.project"), ["languages"]))
    assert "map<string, int64>" in languages


def test_coerce_handles_nested_temporals_and_variant_passthrough() -> None:
    history_type = table_schema("gold.outreach").column_type("history")
    coerced = coerce(
        [{"state": "sent", "ts": "2026-07-15T08:00:00+00:00", "actor": "x"}], history_type
    )
    assert coerced == [
        {"state": "sent", "ts": datetime(2026, 7, 15, 8, 0, tzinfo=UTC), "actor": "x"}
    ]
    incorporation = table_schema("silver.company").column_type("incorporation_date")
    assert coerce("2026-06-20", incorporation) == date(2026, 6, 20)
    payload_type = table_schema("bronze.github_users_raw").column_type("payload")
    payload: Json = {"created_at": "2026-01-01T00:00:00+00:00"}
    assert coerce(payload, payload_type) == payload


def test_parse_type_round_trips_the_tricky_shapes() -> None:
    assert parse_type("MAP<STRING,BIGINT>") == parse_type("MAP<STRING, BIGINT>")
    assert isinstance(parse_type("ARRAY<FLOAT>"), Array)


def test_coerce_rows_types_temporal_cells_and_passes_typed_ones_through() -> None:
    # Rows assembled from JSONL carry ISO strings where the DDL says
    # TIMESTAMP; Parquet staging needs real datetimes (the venture builder
    # passes prior-state created_at straight through).
    typed = coerce_rows(
        "gold.venture",
        [
            {
                "venture_id": "v1",
                "anchor_type": "repo",
                "anchor_id": "p1",
                "name": "GraspLab",
                "status": "sourced",
                "created_at": "2026-07-15T08:00:00+00:00",
                "updated_at": datetime(2026, 7, 15, 8, 0, tzinfo=UTC),
            }
        ],
    )
    assert typed[0]["created_at"] == datetime(2026, 7, 15, 8, 0, tzinfo=UTC)
    assert typed[0]["updated_at"] == datetime(2026, 7, 15, 8, 0, tzinfo=UTC)
    assert typed[0]["name"] == "GraspLab"


def test_coerce_rows_normalizes_column_order_across_a_batch() -> None:
    # Arrow staging compares key order, so a freshly built row and a row
    # copied from JSONL (sorted keys) must come out identically ordered.
    fresh = {
        "venture_id": "v1",
        "anchor_type": "repo",
        "anchor_id": "p1",
        "name": "GraspLab",
        "status": "sourced",
        "created_at": datetime(2026, 7, 15, 8, 0, tzinfo=UTC),
        "updated_at": datetime(2026, 7, 15, 8, 0, tzinfo=UTC),
    }
    from_jsonl = dict(sorted(fresh.items()))
    typed = coerce_rows("gold.venture", [fresh, from_jsonl])
    assert list(typed[0]) == list(typed[1])
    assert list(typed[0]) == [
        column for column in table_schema("gold.venture").column_names if column in fresh
    ]
