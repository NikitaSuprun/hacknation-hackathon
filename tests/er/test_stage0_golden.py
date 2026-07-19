# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""T6 golden: fixture bronze rows normalize byte-exact into the committed PSRs."""

import json
from typing import Final

from contracts.models import Json
from er.normalize import (
    country_from_location,
    github_psrs,
    normalize_bronze,
    source_key_hash,
    suppressed_keys,
)
from er.pipeline import ErInputs
from fixtures.build import SUPPRESSED_KEY_HASH
from tests.er.conftest import fixture_lines, fixture_rows, render

# Fixture-only identities with no bronze source: openalex WeiB (fixture-seeded
# author), the enrichment site profile, and the Jonas Keller officer whose SOGC
# text is not in the bronze sample. They can never come out of stage 0.
EXPECTED_EXCLUDED: Final[set[tuple[str, str]]] = {
    ("openalex_author", "A5000000003"),
    ("enrichment", "aisha-patel-site"),
    ("zefix_officer", "CHE-987.654.321:keller jonas"),
}


def _bronze_tables(inputs: ErInputs) -> dict[str, list[dict[str, Json]]]:
    return {
        "bronze.github_users_raw": inputs.github_users,
        "bronze.github_commits_raw": inputs.github_commits,
        "bronze.github_repos_raw": inputs.github_repos,
        "bronze.arxiv_papers_raw": inputs.arxiv_papers,
        "bronze.openalex_works_raw": inputs.openalex_works,
        "bronze.zefix_companies_raw": inputs.zefix_companies,
        "bronze.zefix_sogc_raw": inputs.zefix_sogc,
    }


def test_stage0_reproduces_fixture_psr_bytes(inputs: ErInputs) -> None:
    records = normalize_bronze(_bronze_tables(inputs), suppressed=frozenset())
    produced = {record.source_record_id: record for record in records}
    expected = {
        str(row["source_record_id"]): line
        for line in fixture_lines("silver.person_source_record")
        if (row := json.loads(line))
    }
    excluded = {
        (str(row["source"]), str(row["source_key"]))
        for row in fixture_rows("silver.person_source_record")
        if str(row["source_record_id"]) not in produced
    }
    assert excluded == EXPECTED_EXCLUDED
    assert set(produced) <= set(expected)
    assert len(produced) == 9
    for source_record_id, record in produced.items():
        row = record.to_row()
        # MASK: fixture keyword constants are narrative-authored and not
        # derivable from bronze (verified); the derivation rule is unit-tested
        # separately in test_github_keywords_are_lowercased_repo_topics.
        row["keywords"] = json.loads(expected[source_record_id])["keywords"]
        assert render(row) == expected[source_record_id], source_record_id


def test_stage0_is_idempotent(inputs: ErInputs) -> None:
    tables = _bronze_tables(inputs)
    first = normalize_bronze(tables, suppressed=frozenset())
    second = normalize_bronze(tables, suppressed=frozenset())
    assert [r.to_row() for r in first] == [r.to_row() for r in second]


def test_github_keywords_are_lowercased_repo_topics(inputs: ErInputs) -> None:
    records = github_psrs(inputs.github_users, inputs.github_commits, inputs.github_repos)
    by_key = {record.source_key: record for record in records}
    # Lena authored a commit in grasp-anything, whose topics she inherits.
    assert by_key["501001"].keywords == ("foundation-models", "manipulation", "robotics")
    # Wei has no commit rows in bronze, so no topic keywords.
    assert by_key["501002"].keywords == ()


def test_country_gazetteer() -> None:
    assert country_from_location("Zurich, Switzerland") == "CH"
    assert country_from_location("Munich") == "DE"
    assert country_from_location("Atlantis") is None
    assert country_from_location(None) is None


def test_suppression_blocks_normalization(inputs: ErInputs) -> None:
    assert source_key_hash("999001") == SUPPRESSED_KEY_HASH
    suppressed = suppressed_keys(
        [{"source": "github", "source_key_hash": source_key_hash("501001")}]
    )
    records = normalize_bronze(_bronze_tables(inputs), suppressed=suppressed)
    keys = {(record.source, record.source_key) for record in records}
    assert ("github", "501001") not in keys
    assert ("github", "501002") in keys
