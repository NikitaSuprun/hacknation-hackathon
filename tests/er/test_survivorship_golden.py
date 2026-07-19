# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""T10 golden: survivorship reproduces the fixture persons, scores, backfill."""

from typing import Final

from er.models import psr_view
from er.pipeline import ErInputs, ErOutputs
from er.survivorship import backfill_person_id, data_quality_score
from fixtures import build as fx
from tests.er.conftest import fixture_lines, render

EXPECTED_SCORES: Final[dict[str, float]] = {
    fx.LENA: 0.9,
    fx.WEI_A: 0.7,
    fx.WEI_B: 0.6,
    fx.NILS: 0.7,
    fx.AISHA: 0.6,
    fx.JONAS_DEV: 0.5,
    fx.JONAS_LAW: 0.5,
    fx.MIRA: 0.7,
    fx.NOAH: 0.5,
}


def test_person_rows_reproduce_fixture_bytes(scratch_outputs: ErOutputs) -> None:
    produced = list(scratch_outputs.tables["silver.person"])
    expected = fixture_lines("silver.person")
    assert len(produced) == len(expected) == 9
    for produced_row, line in zip(produced, expected, strict=True):
        row = dict(produced_row)
        if row["person_id"] == fx.WEI_A:
            # MASK (fixture drift): the fixture person has location null even
            # though Wei's github PSR carries 'Zurich'; the engine surfaces it.
            assert row["location"] == "Zurich"
            row["location"] = None
        assert render(row) == line


def test_all_nine_data_quality_scores(scratch_outputs: ErOutputs) -> None:
    scores = {
        str(row["person_id"]): row["data_quality_score"]
        for row in scratch_outputs.tables["silver.person"]
    }
    assert scores == EXPECTED_SCORES


def test_score_formula_components(inputs: ErInputs) -> None:
    views = {str(row["source_record_id"]): psr_view(row) for row in inputs.psr_rows}
    # Three independent sources cap at 0.9.
    assert (
        data_quality_score(
            [views[fx.PSR_LENA_GITHUB], views[fx.PSR_LENA_OPENALEX], views[fx.PSR_LENA_ZEFIX]]
        )
        == 0.9
    )
    # Enrichment never counts as independent; the ORCID keeps Aisha at 0.6.
    assert data_quality_score([views[fx.PSR_AISHA_OPENALEX], views[fx.PSR_AISHA_ENRICHMENT]]) == 0.6
    # A lone github identity carries no verified identifier.
    assert data_quality_score([views[fx.PSR_JONAS_GITHUB]]) == 0.5


def test_backfill_updates_only_changed_rows(inputs: ErInputs) -> None:
    facts = [dict(row) for row in inputs.contributions]
    facts[0]["person_id"] = None
    active = {
        str(row["source_record_id"]): str(row["person_id"])
        for row in inputs.link_rows
        if row["status"] == "active"
    }
    changed = backfill_person_id(facts, active)
    assert len(changed) == 1
    assert changed[0]["contribution_id"] == facts[0]["contribution_id"]
    assert changed[0]["person_id"] == active[str(facts[0]["source_record_id"])]


def test_conflicts_are_surfaced_not_resolved(scratch_outputs: ErOutputs) -> None:
    conflict_fields = {
        (conflict.person_id, conflict.field) for conflict in scratch_outputs.conflicts
    }
    # Lena is both ETH-affiliated and a GraspLab officer: flagged, not decided.
    assert (fx.LENA, "affiliation") in conflict_fields
