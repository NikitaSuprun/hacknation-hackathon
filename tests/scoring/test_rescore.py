# Copyright (c) 2026 Venture Hunt. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Rescore: the two-row fixture history, duplicate no-op, schema hard-check."""

import json
from collections.abc import Iterator

import pytest

from contracts.interfaces import InstitutionScorer
from contracts.models import Json
from fixtures import build
from scoring import scripted
from scoring.categories.base import scripted_registry
from scoring.deps import ScoringDeps
from scoring.institution_seed import build_institution_rows
from scoring.institutions import SeededInstitutionScorer
from scoring.memo import MemoRequest
from scoring.rescore import (
    InterviewInvalidError,
    RescoreOutcome,
    RescoreRequest,
    ingest_interview,
)
from scoring.serialize import to_jsonl_lines
from scoring.snapshot import GoldInputs, Row, SilverSnapshot
from scoring.stage_a import (
    ScoreCalibration,
    StageAContext,
    collab_extras,
    feature_bundle,
    run_stage_a,
    venture_view,
)
from scrapers.common.jsonutil import as_mapping
from tests.scoring.conftest import MEMBER_IDS, golden_lines, golden_text


def make_context(
    silver: SilverSnapshot,
    gold: GoldInputs,
    prior: tuple[Row, ...],
    calibration: ScoreCalibration,
) -> StageAContext:
    return StageAContext(
        venture=venture_view(gold.ventures[0], gold.members, collab_extras(silver, MEMBER_IDS)),
        features=feature_bundle(gold.features),
        weights_row=gold.weights[0],
        profile_id=build.IDEAL_ID,
        registry=scripted_registry(scripted.fixture_category_results()),
        prior_scores=prior,
        model_version=scripted.SCORER_MODEL_VERSION,
        calibration=calibration,
    )


def scorer(deps: ScoringDeps) -> InstitutionScorer:
    return SeededInstitutionScorer(list(build_institution_rows(now=scripted.FIXTURE_NOW)), deps.log)


def memo_request() -> MemoRequest:
    return MemoRequest(
        venture_id=build.GRASP_VENTURE,
        thesis_id=build.THESIS_ID,
        run_id=build.RUN_ID,
        context={"name": "GraspLab"},
        model_version=scripted.MEMO_MODEL_VERSION,
        prior_memos=(),
    )


def id_sequence(*ids: str) -> Iterator[str]:
    return iter(ids)


def first_run_row(silver: SilverSnapshot, gold: GoldInputs) -> Row:
    context = make_context(silver, gold, (), scripted.FIXTURE_CALIBRATION_OLD)
    result = run_stage_a(
        context, clock=lambda: scripted.FIXTURE_OLD_NOW, id_factory=lambda: build.SCORE_OLD_ID
    )
    return as_mapping(json.loads(to_jsonl_lines([result.score_row]).strip()))


def ingest(
    silver: SilverSnapshot,
    gold: GoldInputs,
    deps: ScoringDeps,
    prior_score: Row,
    prior_runs: tuple[Row, ...],
    run_id: str,
) -> RescoreOutcome:
    ids = id_sequence(build.SCORE_LATEST_ID, build.MEMO_ID, run_id)
    request = RescoreRequest(
        interview=gold.interviews[0],
        context=make_context(silver, gold, (prior_score,), scripted.FIXTURE_CALIBRATION),
        memo=memo_request(),
        prior_runs=prior_runs,
        snapshot=silver,
    )
    return ingest_interview(
        request,
        llm=deps.llm,
        institutions=scorer(deps),
        clock=deps.clock,
        id_factory=lambda: next(ids),
    )


def test_interview_reproduces_the_two_row_fixture_history(
    silver: SilverSnapshot, gold: GoldInputs, deps: ScoringDeps
) -> None:
    old_row = first_run_row(silver, gold)
    outcome = ingest(silver, gold, deps, old_row, (), "run-0001")
    assert outcome.status == "ok"
    # New latest first, flipped pre-interview row second - the fixture bytes.
    # The rescore touches only the GraspLab venture, so the WS-G hackathon
    # venture's score row (same file) is filtered out of the expectation.
    grasp_score_lines = "".join(
        line
        for line in golden_lines("gold.venture_score")
        if json.loads(line)["venture_id"] == build.GRASP_VENTURE
    )
    assert to_jsonl_lines(list(outcome.score_rows)) == grasp_score_lines
    assert to_jsonl_lines(list(outcome.memo_rows)) == golden_text("gold.memo")
    assert outcome.funding_signal == "none_found"
    assert outcome.run_row["status"] == "ok"
    assert outcome.run_row["trigger"] == "interview"


def test_duplicate_ingest_is_a_no_op(
    silver: SilverSnapshot, gold: GoldInputs, deps: ScoringDeps
) -> None:
    old_row = first_run_row(silver, gold)
    outcome = ingest(silver, gold, deps, old_row, (), "run-0001")
    prior_run: Row = as_mapping(json.loads(to_jsonl_lines([outcome.run_row]).strip()))
    duplicate = ingest(silver, gold, deps, old_row, (prior_run,), "run-0002")
    assert duplicate.status == "skipped_duplicate"
    assert duplicate.score_rows == ()
    assert duplicate.memo_rows == ()
    assert duplicate.run_row["status"] == "skipped_duplicate"


def test_invalid_extracted_payload_fails_hard(
    silver: SilverSnapshot, gold: GoldInputs, deps: ScoringDeps
) -> None:
    interview: dict[str, Json] = dict(gold.interviews[0])
    interview["extracted"] = {"education": [{"degree": "PhD"}]}  # no schema_version
    request = RescoreRequest(
        interview=interview,
        context=make_context(silver, gold, (), scripted.FIXTURE_CALIBRATION),
        memo=memo_request(),
        prior_runs=(),
        snapshot=silver,
    )
    with pytest.raises(InterviewInvalidError, match="schema_version"):
        ingest_interview(
            request,
            llm=deps.llm,
            institutions=scorer(deps),
            clock=deps.clock,
            id_factory=lambda: "run-x",
        )


def test_traction_claims_release_the_cap_marker(
    silver: SilverSnapshot, gold: GoldInputs, deps: ScoringDeps
) -> None:
    old_row = first_run_row(silver, gold)
    outcome = ingest(silver, gold, deps, old_row, (), "run-0001")
    versions = outcome.run_row["input_versions"]
    assert isinstance(versions, dict)
    assert versions["trigger"] == "interview"
    assert isinstance(versions["fingerprint"], str)
