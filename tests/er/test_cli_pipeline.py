# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""T13: the credential-free CLI path and incremental idempotence."""

from collections.abc import Iterator
from dataclasses import replace

import pytest
import structlog
from typer.testing import CliRunner

from contracts.models import Json
from er.__main__ import app
from er.offline import offline_deps, offline_inputs
from er.pipeline import ALL_STAGES, run_pipeline
from fixtures import build as fx
from fixtures.build import T_INGESTED, T_SCRAPED
from tests.er.conftest import as_json_rows
from tools import ids

runner = CliRunner()


@pytest.fixture(autouse=True)
def _unbind_captured_stderr() -> Iterator[None]:  # pyright: ignore[reportUnusedFunction] - autouse fixture
    # configure_logging() inside the CLI binds structlog to the CliRunner's
    # temporary stderr; reset afterwards so later tests never write to a
    # closed capture stream.
    yield
    structlog.reset_defaults()


def test_fixtures_dry_run_end_to_end() -> None:
    result = runner.invoke(app, ["run", "--fixtures", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "silver.person_source_record: 9 rows" in result.output
    assert "silver.person: 7 rows" in result.output
    assert "silver.person_connection: 2 rows" in result.output
    assert "silver.person_source_link: 0 rows" in result.output


def test_fixtures_dry_run_with_embeddings() -> None:
    result = runner.invoke(app, ["run", "--fixtures", "--dry-run", "--with-embeddings"])
    assert result.exit_code == 0, result.output
    assert "gold.person_features: 7 rows" in result.output


def test_stage_selection() -> None:
    result = runner.invoke(app, ["run", "--fixtures", "--dry-run", "--stages", "0"])
    assert result.exit_code == 0, result.output
    assert "silver.person_source_record: 9 rows" in result.output
    assert "silver.person_source_link: 0 rows" in result.output
    assert "silver.person" not in result.output.replace("silver.person_", "")


def test_unmerge_dry_run_plans_without_credentials() -> None:
    link_id = ids.link_id(fx.JONAS_DEV, fx.PSR_JONAS_GITHUB, "seed_fixture")
    result = runner.invoke(
        app,
        [
            "unmerge",
            "--fixtures",
            "--dry-run",
            "--link-id",
            link_id,
            "--to-person",
            fx.JONAS_LAW,
            "--reason",
            "test",
        ],
    )
    assert result.exit_code == 0, result.output
    assert fx.PSR_JONAS_GITHUB in result.output
    assert "gold.venture_score" in result.output


def test_new_bronze_user_flows_to_minted_person_and_rerun_is_idempotent() -> None:
    inputs = offline_inputs()
    synthetic: dict[str, Json] = {
        "user_id": 999777,
        "login": "zaraquintana",
        "payload": {"name": "Zara Quintana", "email": None, "location": None},
        "content_hash": "0" * 64,
        "source_url": "https://api.github.com/users/zaraquintana",
        "scraped_at": T_SCRAPED,
        "ingested_at": T_INGESTED,
        "scrape_run_id": "test-run",
    }
    grown = replace(inputs, github_users=[*inputs.github_users, synthetic])
    deps = offline_deps(inputs)
    first = run_pipeline(grown, deps, stages=ALL_STAGES)
    assert len(first.tables["silver.person_source_record"]) == 10
    (new_link,) = first.tables["silver.person_source_link"]
    assert new_link["match_method"] == "seed_fixture"
    persons = {str(row["person_id"]) for row in first.tables["silver.person"]}
    assert str(new_link["person_id"]) in persons
    assert len(persons) == 8
    produced_psrs = as_json_rows(first.tables["silver.person_source_record"])
    new_psrs = [row for row in produced_psrs if row["source_key"] == "999777"]
    assert len(new_psrs) == 1
    second_inputs = replace(
        grown,
        psr_rows=[*inputs.psr_rows, *new_psrs],
        link_rows=[*inputs.link_rows, *as_json_rows(first.tables["silver.person_source_link"])],
    )
    second = run_pipeline(second_inputs, deps, stages=ALL_STAGES)
    assert second.tables["silver.person_source_link"] == []
    assert second.tables["ops.er_review_queue"] == []
