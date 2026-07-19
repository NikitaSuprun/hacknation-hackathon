# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Offline tests for DDL rendering, splitting, and idempotency classification."""

from tools.apply_ddl import DDL_DIR, is_skippable_error, render, split_statements


def test_render_substitutes_catalog() -> None:
    assert render("USE CATALOG ${catalog};", "dealflow_dev") == "USE CATALOG dealflow_dev;"


def test_split_drops_comment_only_chunks() -> None:
    text = "-- header\nUSE CATALOG x;\n-- trailing comment\n\nCREATE SCHEMA y;\n"
    statements = split_statements(text)
    assert len(statements) == 2
    assert statements[0].endswith("USE CATALOG x")
    assert statements[1].endswith("CREATE SCHEMA y")


def test_split_strips_inline_comments() -> None:
    text = "CREATE TABLE t (\n  a STRING -- key\n);"
    assert split_statements(text) == ["CREATE TABLE t (\n  a STRING\n)"]


def test_semicolon_inside_comment_does_not_split() -> None:
    # Regression: bronze._rejects carries "…never crash a run; they land here"
    # in its comment, which used to truncate the statement mid-parenthesis.
    text = (
        "CREATE TABLE IF NOT EXISTS bronze._rejects (  -- never crash a run; they land here\n"
        "  source STRING, ingested_at TIMESTAMP\n"
        ");"
    )
    statements = split_statements(text)
    assert len(statements) == 1
    assert statements[0].endswith(")")
    assert "source STRING" in statements[0]


def test_all_ddl_files_split_cleanly() -> None:
    files = sorted(DDL_DIR.glob("*.sql"))
    assert [f.name for f in files] == [
        "00_catalog.sql",
        "10_bronze.sql",
        "20_silver.sql",
        "30_gold.sql",
        "40_ops.sql",
        "50_views.sql",
    ]
    for path in files:
        statements = split_statements(render(path.read_text(encoding="utf-8"), "dealflow_dev"))
        assert statements, path.name
        assert all("${catalog}" not in s for s in statements), path.name


def test_constraint_already_exists_is_skippable() -> None:
    statement = "ALTER TABLE silver.person ADD CONSTRAINT chk_person_status CHECK (1=1)"
    assert is_skippable_error(statement, "Constraint 'chk_person_status' already exists")
    assert not is_skippable_error(statement, "PARSE_SYNTAX_ERROR near CHECK")
    assert not is_skippable_error("CREATE TABLE t (a STRING)", "already exists")
