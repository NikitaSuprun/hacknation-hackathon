# Copyright (c) 2026 Venture Hunt. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""T-QA: golden-set precision report and fact corroboration."""

from contracts.models import Json
from er.offline import frozen_clock
from er.pipeline import ErOutputs
from er.quality import corroborate, linked_pairs, precision_report
from tests.er.conftest import as_json_rows, fixture_rows


def test_fixture_run_scores_perfect_precision(scratch_outputs: ErOutputs) -> None:
    produced = as_json_rows(scratch_outputs.tables["silver.person_source_link"])
    golden = fixture_rows("silver.person_source_link")
    report = precision_report(produced, golden, cycle_id="test-cycle", clock=frozen_clock)
    assert report["er_precision"] == 1.0
    assert report["false_merge_rate"] == 0.0
    assert report["cycle_id"] == "test-cycle"
    assert report["source"] == "er"
    assert linked_pairs(produced) == linked_pairs(golden)


def test_false_merge_is_detected() -> None:
    golden = [
        {"person_id": "p1", "source_record_id": "a", "status": "active"},
        {"person_id": "p1", "source_record_id": "b", "status": "active"},
        {"person_id": "p2", "source_record_id": "c", "status": "active"},
    ]
    produced = [
        {"person_id": "x", "source_record_id": "a", "status": "active"},
        {"person_id": "x", "source_record_id": "b", "status": "active"},
        {"person_id": "x", "source_record_id": "c", "status": "active"},
    ]
    report = precision_report(produced, golden, cycle_id="c", clock=frozen_clock)
    assert report["er_precision"] == round(1 / 3, 4)
    assert report["false_merge_rate"] == round(2 / 3, 4)


def test_corroboration_promotes_only_multi_source_facts() -> None:
    facts: list[dict[str, Json]] = [
        {
            "contribution_id": "c1",
            "project_id": "proj-1",
            "source_record_id": "psr-gh",
            "corroboration_count": 0,
            "is_provisional": False,
        },
        {
            "contribution_id": "c2",
            "project_id": "proj-2",
            "source_record_id": "psr-gh2",
            "corroboration_count": 1,
            "is_provisional": True,
        },
    ]
    changed = corroborate(
        facts,
        artifact_col="project_id",
        psr_sources={"psr-gh": "github", "psr-gh2": "github"},
        attesting_sources={
            "proj-1": frozenset({"openalex_author"}),  # cross-linked paper attests
            "proj-2": frozenset({"enrichment"}),  # enrichment never counts
        },
    )
    by_id = {str(row["contribution_id"]): row for row in changed}
    assert by_id["c1"]["corroboration_count"] == 2
    assert by_id["c1"]["is_provisional"] is False
    assert "c2" not in by_id  # already 1/provisional; enrichment adds nothing
