# Copyright (c) 2026 Venture Hunt. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Golden constants and DDL-reality checks for the WS-G deterministic ER rules."""

import re
from typing import Final

from scrapers.hacknation.er_rules import (
    CONFIDENCE_D7,
    CONFIDENCE_D8,
    D7_SQL,
    D8_SQL,
    MATCH_METHOD_D7,
    MATCH_METHOD_D8,
)
from tools.ddl_registry import registry, table_schema

AUTO_LINK_FLOOR: Final[float] = 0.90

_TABLE_REF: Final[re.Pattern[str]] = re.compile(r"\b(?:bronze|silver|gold|ops)\.[a-z_]+")


def test_frozen_constants() -> None:
    assert MATCH_METHOD_D7 == "det_linkedin"
    assert CONFIDENCE_D7 == 0.97
    assert MATCH_METHOD_D8 == "det_hn_repo"
    assert CONFIDENCE_D8 == 0.90
    assert MATCH_METHOD_D7 != MATCH_METHOD_D8


def test_confidences_clear_the_auto_link_floor() -> None:
    assert CONFIDENCE_D7 >= AUTO_LINK_FLOOR
    assert CONFIDENCE_D8 >= AUTO_LINK_FLOOR


def test_sql_embeds_its_frozen_constants() -> None:
    assert f"'{MATCH_METHOD_D7}' AS match_method" in D7_SQL
    assert "0.97 AS match_confidence" in D7_SQL
    assert f"'{MATCH_METHOD_D8}' AS match_method" in D8_SQL
    assert "0.90 AS match_confidence" in D8_SQL


def test_d7_references_only_ddl_tables() -> None:
    found = set(_TABLE_REF.findall(D7_SQL))
    assert found == {"silver.person_source_record", "silver.person_source_link"}
    for table in found:
        assert table in registry()


def test_d8_references_only_ddl_tables() -> None:
    found = set(_TABLE_REF.findall(D8_SQL))
    assert found == {
        "bronze.hacknation_projects_raw",
        "silver.project",
        "silver.contribution",
        "silver.person_source_record",
        "silver.person_source_link",
    }
    for table in found:
        assert table in registry()


def test_psr_columns_the_rules_touch_exist() -> None:
    psr = table_schema("silver.person_source_record").column_names
    for column in ("linkedin_url", "source", "source_record_id", "name_norm", "source_key"):
        assert column in psr


def test_join_columns_on_the_other_tables_exist() -> None:
    link = table_schema("silver.person_source_link").column_names
    assert {"person_id", "source_record_id", "status"} <= set(link)
    project = table_schema("silver.project").column_names
    assert {"project_id", "full_name", "source_platform"} <= set(project)
    contribution = table_schema("silver.contribution").column_names
    assert {"project_id", "source_record_id", "contribution_share", "commit_count"} <= set(
        contribution
    )


def test_sql_is_session_catalog_and_names_the_engine_seams() -> None:
    for sql in (D7_SQL, D8_SQL):
        assert "${catalog}" not in sql
        assert "SELECT" in sql
        assert "NOT EXISTS" in sql
        assert "status = 'active'" in sql
    assert "LATERAL variant_explode" in D8_SQL
    assert "jaro_winkler(a.name_norm, b.name_norm) >= 0.9" in D8_SQL
