"""Pure-logic tests for the sink: hashing, staging, and generated MERGE SQL."""

from typing import Final

from contracts.interfaces import Sink
from contracts.models import SinkRow, UpsertResult
from tools._arrow import arrow_schema
from tools.db import (
    SUPPRESSION_RULES,
    DatabricksSink,
    MergeSpec,
    build_merge_sql,
    build_suppressed_count_sql,
    canonical_json,
    content_hash,
    parquet_bytes,
    prepare_rows,
    stage_table,
)
from tools.ddl_registry import table_schema
from tools.settings import DatabricksSettings

_SETTINGS: Final[DatabricksSettings] = DatabricksSettings(
    host="https://example.cloud.databricks.com",
    client_id="cid",
    client_secret="secret",
    warehouse_id="wh",
)


def test_canonical_json_sorts_and_compacts() -> None:
    assert canonical_json({"b": 1, "a": [1, 2]}) == '{"a":[1,2],"b":1}'


def test_content_hash_is_stable_and_order_insensitive() -> None:
    first = content_hash({"b": 1, "a": 2})
    second = content_hash({"a": 2, "b": 1})
    assert first == second
    assert content_hash({"a": 2, "b": 2}) != first


def test_prepare_rows_encodes_variants_only() -> None:
    rows: list[SinkRow] = [{"id": 1, "payload": {"b": 1, "a": 2}, "note": None}]
    prepared = prepare_rows(rows, frozenset({"payload", "note"}))
    assert prepared[0]["payload"] == '{"a":2,"b":1}'
    assert prepared[0]["note"] is None
    assert prepared[0]["id"] == 1
    assert rows[0]["payload"] == {"b": 1, "a": 2}


def test_merge_sql_hash_table_with_suppression() -> None:
    sql = build_merge_sql(
        MergeSpec(
            catalog="dealflow_dev",
            table="bronze.github_users_raw",
            columns=["user_id", "login", "payload", "content_hash", "source_url"],
            keys=["user_id"],
            staged_path="/Volumes/dealflow_dev/ops/staging/x/y.parquet",
            variant_cols=frozenset({"payload"}),
            complex_cols=frozenset(),
            hash_col="content_hash",
        )
    )
    assert "MERGE INTO dealflow_dev.bronze.github_users_raw t" in sql
    assert "parse_json(src.payload) AS payload" in sql
    assert "es.source = 'github'" in sql
    assert "sha2(CAST(src.user_id AS STRING), 256)" in sql
    assert "WHEN MATCHED AND (t.content_hash <> s.content_hash)" in sql
    assert "WHEN NOT MATCHED THEN INSERT" in sql


def test_merge_sql_no_hash_table_compares_whole_row() -> None:
    sql = build_merge_sql(
        MergeSpec(
            catalog="dealflow_dev",
            table="silver.person_source_link",
            columns=["link_id", "person_id", "evidence", "emails"],
            keys=["link_id"],
            staged_path="/Volumes/p.parquet",
            variant_cols=frozenset({"evidence"}),
            complex_cols=frozenset({"emails"}),
            hash_col="content_hash",
        )
    )
    expected = (
        "MERGE INTO dealflow_dev.silver.person_source_link t\n"
        "USING (SELECT src.link_id, src.person_id, parse_json(src.evidence) AS evidence, "
        "src.emails FROM parquet.`/Volumes/p.parquet` src) s\n"
        "ON t.link_id = s.link_id\n"
        "WHEN MATCHED AND (NOT (t.person_id <=> s.person_id "
        "AND to_json(t.evidence) <=> to_json(s.evidence) "
        "AND to_json(t.emails) <=> to_json(s.emails))) THEN UPDATE SET "
        "t.person_id = s.person_id, t.evidence = s.evidence, t.emails = s.emails\n"
        "WHEN NOT MATCHED THEN INSERT (link_id, person_id, evidence, emails) "
        "VALUES (s.link_id, s.person_id, s.evidence, s.emails)"
    )
    assert sql == expected


def test_psr_suppression_uses_per_row_source() -> None:
    rule = SUPPRESSION_RULES["silver.person_source_record"]
    sql = build_suppressed_count_sql("dealflow_dev", "/v.parquet", rule)
    assert "es.source = src.source" in sql
    assert "sha2(CAST(src.source_key AS STRING), 256)" in sql


def test_stage_table_builds_ddl_typed_columns() -> None:
    columns = ["project_id", "stars", "languages", "topics"]
    rows: list[SinkRow] = [
        {
            "project_id": "p1",
            "stars": 8200,
            "languages": {"Python": 12, "Rust": 3},
            "topics": ["robotics"],
        },
        {"project_id": "p2", "stars": None, "languages": None, "topics": []},
    ]
    staging = arrow_schema(table_schema("silver.project"), columns)
    arrow_table = stage_table(rows, staging, "silver.project")
    rendered = str(arrow_table.schema)
    assert "stars: int32" in rendered
    assert "languages: map<string, int64>" in rendered
    assert "topics: list<item: string>" in rendered
    assert len(parquet_bytes(arrow_table)) > 0


def test_sink_satisfies_protocol() -> None:
    sink: Sink = DatabricksSink(_SETTINGS)
    result: UpsertResult = sink.upsert("bronze.github_users_raw", [], ["user_id"])
    assert result.inserted == 0
    assert result.suppressed == 0
