# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""T10: unmerge reproduces the Jonas retracted + corrective fixture rows."""

import json

import pytest

from contracts.models import Json
from er.offline import frozen_clock
from er.unmerge import UnknownLinkError, UnmergeRequest, plan_unmerge
from fixtures import build as fx
from tests.er.conftest import fixture_lines, render


def _fixture_link(predicate: str, value: str) -> dict[str, Json]:
    for line in fixture_lines("silver.person_source_link"):
        row = json.loads(line)
        if row[predicate] == value:
            return row
    message = f"no fixture link with {predicate}={value}"
    raise AssertionError(message)


def _pre_unmerge_link() -> dict[str, Json]:
    """The retracted fixture link, rewound to its pre-unmerge active state."""
    row = _fixture_link("status", "retracted")
    return {
        **row,
        "status": "active",
        "retracted_at": None,
        "retracted_by": None,
        "retracted_reason": None,
    }


def test_unmerge_reproduces_fixture_bytes() -> None:
    active = _pre_unmerge_link()
    request = UnmergeRequest(
        link_id=str(active["link_id"]),
        to_person_id=fx.JONAS_LAW,
        reason="Different person: Berlin developer vs Zug advisor",
        reviewer_note="SHAB officer is the Zug advisor",
        actor="analyst",
    )
    outcome = plan_unmerge(
        request,
        [active],
        clock=frozen_clock,
        pipeline_version=fx.PIPELINE_VERSION,
        catalog="dealflow_dev",
    )
    retracted_line = next(
        line
        for line in fixture_lines("silver.person_source_link")
        if json.loads(line)["status"] == "retracted"
    )
    corrective_line = next(
        line
        for line in fixture_lines("silver.person_source_link")
        if json.loads(line)["match_method"] == "human_review"
    )
    assert render(outcome.retracted_link) == retracted_line
    assert render(outcome.corrective_link) == corrective_line
    assert outcome.source_record_id == fx.PSR_JONAS_ZEFIX
    assert outcome.affected_person_ids == (fx.JONAS_DEV, fx.JONAS_LAW)


def test_invalidation_statements_target_both_persons() -> None:
    active = _pre_unmerge_link()
    request = UnmergeRequest(
        link_id=str(active["link_id"]),
        to_person_id=fx.JONAS_LAW,
        reason="wrong person",
        reviewer_note="note",
        actor="analyst",
    )
    outcome = plan_unmerge(
        request,
        [active],
        clock=frozen_clock,
        pipeline_version=fx.PIPELINE_VERSION,
        catalog="dealflow_dev",
    )
    assert len(outcome.invalidation_statements) == 2
    for statement, person in zip(
        outcome.invalidation_statements, outcome.affected_person_ids, strict=True
    ):
        assert "gold.venture_score" in statement
        assert "is_latest = false" in statement
        assert person in statement


def test_unknown_or_retracted_link_raises() -> None:
    retracted = _fixture_link("status", "retracted")
    request = UnmergeRequest(
        link_id=str(retracted["link_id"]),
        to_person_id=fx.JONAS_LAW,
        reason="r",
        reviewer_note="n",
        actor="analyst",
    )
    with pytest.raises(UnknownLinkError):
        plan_unmerge(
            request,
            [retracted],
            clock=frozen_clock,
            pipeline_version=fx.PIPELINE_VERSION,
            catalog="dealflow_dev",
        )
