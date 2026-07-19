# Copyright (c) 2026 Venture Hunt. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Venture gaps: golden bytes, ranking, filled fields, the cap."""

from fixtures import build
from scoring.gaps import GAP_CATALOG, MAX_GAPS, build_gaps
from scoring.scripted import FIXTURE_NOW
from scoring.serialize import to_jsonl_lines
from scoring.snapshot import GoldInputs
from tests.scoring.conftest import golden_text


def test_gap_rows_byte_reproduce_golden_file(gold: GoldInputs) -> None:
    rows = build_gaps(build.GRASP_VENTURE, gold.weights[0], frozenset(), FIXTURE_NOW)
    assert to_jsonl_lines(rows) == golden_text("gold.venture_gaps")


def test_ranking_is_weight_times_importance(gold: GoldInputs) -> None:
    rows = build_gaps(build.GRASP_VENTURE, gold.weights[0], frozenset(), FIXTURE_NOW)
    # w_traction*0.9 = 0.09 outranks w_market*0.7 = 0.07.
    assert [row["field"] for row in rows] == ["traction.revenue", "market.tam"]


def test_filled_fields_are_dropped(gold: GoldInputs) -> None:
    rows = build_gaps(
        build.GRASP_VENTURE, gold.weights[0], frozenset({"traction.revenue"}), FIXTURE_NOW
    )
    assert [row["field"] for row in rows] == ["market.tam"]


def test_catalog_owns_the_exact_question_wording() -> None:
    questions = {spec.field: spec.question_text for spec in GAP_CATALOG}
    assert questions["traction.revenue"] == "Do you have paying pilots or revenue today?"
    assert (
        questions["market.tam"] == "Which customer segment do you serve first, and how large is it?"
    )


def test_cap_is_eight() -> None:
    assert MAX_GAPS == 8
    assert len(GAP_CATALOG) <= MAX_GAPS
