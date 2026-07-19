# Copyright (c) 2026 Venture Hunt. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Stage A: golden score row, schema hard-check, confidence response, gate."""

import json

import pytest

from contracts.models import CategoryScore, FeatureBundle
from contracts.validation import payload_errors
from fixtures import build
from scoring import scripted
from scoring.categories.base import scripted_registry
from scoring.deps import ScoringDeps
from scoring.serialize import to_jsonl_lines
from scoring.snapshot import GoldInputs, SilverSnapshot
from scoring.stage_a import (
    BreakdownInvalidError,
    ScoreCalibration,
    StageAContext,
    StageAResult,
    collab_extras,
    feature_bundle,
    run_stage_a,
    venture_view,
)
from tests.scoring.conftest import MEMBER_IDS, golden_lines


def make_context(
    silver: SilverSnapshot,
    gold: GoldInputs,
    *,
    calibration: ScoreCalibration | None,
    features: FeatureBundle | None = None,
) -> StageAContext:
    return StageAContext(
        venture=venture_view(gold.ventures[0], gold.members, collab_extras(silver, MEMBER_IDS)),
        features=features if features is not None else feature_bundle(gold.features),
        weights_row=gold.weights[0],
        profile_id=build.IDEAL_ID,
        registry=scripted_registry(scripted.fixture_category_results()),
        prior_scores=(),
        model_version=scripted.SCORER_MODEL_VERSION,
        calibration=calibration,
    )


def run(context: StageAContext, deps: ScoringDeps, score_id: str) -> StageAResult:
    return run_stage_a(context, clock=deps.clock, id_factory=lambda: score_id)


def test_latest_score_row_byte_reproduces_the_fixture(
    silver: SilverSnapshot, gold: GoldInputs, deps: ScoringDeps
) -> None:
    context = make_context(silver, gold, calibration=scripted.FIXTURE_CALIBRATION)
    result = run(context, deps, build.SCORE_LATEST_ID)
    assert to_jsonl_lines([result.score_row]) == golden_lines("gold.venture_score")[0]


def test_emitted_breakdown_passes_the_frozen_schema(
    silver: SilverSnapshot, gold: GoldInputs, deps: ScoringDeps
) -> None:
    result = run(make_context(silver, gold, calibration=None), deps, build.SCORE_LATEST_ID)
    line = to_jsonl_lines([result.score_row]).strip()
    parsed = json.loads(line)
    assert payload_errors("breakdown", parsed["breakdown"]) == []


def test_invalid_category_verdict_fails_hard(
    silver: SilverSnapshot, gold: GoldInputs, deps: ScoringDeps
) -> None:
    results = scripted.fixture_category_results()
    results["schools"] = CategoryScore(
        category="schools",
        score=200.0,  # out of the 0-100 range
        confidence=0.8,
        method="deterministic",
        rationale=None,
        evidence=(),
    )
    context = make_context(silver, gold, calibration=None)
    broken = StageAContext(
        venture=context.venture,
        features=context.features,
        weights_row=context.weights_row,
        profile_id=context.profile_id,
        registry=scripted_registry(results),
        prior_scores=(),
        model_version=context.model_version,
        calibration=None,
    )
    with pytest.raises(BreakdownInvalidError, match="schools"):
        run(broken, deps, build.SCORE_LATEST_ID)


def test_uncalibrated_final_is_the_derived_78_9(
    silver: SilverSnapshot, gold: GoldInputs, deps: ScoringDeps
) -> None:
    result = run(make_context(silver, gold, calibration=None), deps, build.SCORE_LATEST_ID)
    assert result.final_score == 78.9  # fixture pins 78.4 through ScoreCalibration


def test_confidence_drops_when_a_feature_is_removed(
    silver: SilverSnapshot, gold: GoldInputs, deps: ScoringDeps
) -> None:
    full = run(make_context(silver, gold, calibration=None), deps, build.SCORE_LATEST_ID)
    bundle = feature_bundle(gold.features)
    thinned = {
        person_id: {key: value for key, value in features.items() if key != "school_tier"}
        for person_id, features in bundle.person_features.items()
    }
    reduced = make_context(
        silver,
        gold,
        calibration=None,
        features=FeatureBundle(person_features=thinned, venture_features={}),
    )
    thin = run(reduced, deps, build.SCORE_LATEST_ID)
    assert thin.confidence < full.confidence


def test_quality_gate_flips_to_needs_more_data(
    silver: SilverSnapshot, gold: GoldInputs, deps: ScoringDeps
) -> None:
    low = make_context(silver, gold, calibration=ScoreCalibration(final_score=41.0, confidence=0.3))
    result = run(low, deps, build.SCORE_LATEST_ID)
    assert result.quality_tier == "needs_more_data"
    scored = run(
        make_context(silver, gold, calibration=scripted.FIXTURE_CALIBRATION),
        deps,
        build.SCORE_LATEST_ID,
    )
    assert scored.quality_tier == "scored"


def test_prior_latest_rows_are_flipped(
    silver: SilverSnapshot, gold: GoldInputs, deps: ScoringDeps
) -> None:
    prior = tuple(row for row in gold.scores if row.get("is_latest") is True)
    context = make_context(silver, gold, calibration=scripted.FIXTURE_CALIBRATION)
    with_prior = StageAContext(
        venture=context.venture,
        features=context.features,
        weights_row=context.weights_row,
        profile_id=context.profile_id,
        registry=context.registry,
        prior_scores=prior,
        model_version=context.model_version,
        calibration=context.calibration,
    )
    result = run(with_prior, deps, build.SCORE_LATEST_ID)
    assert len(result.flipped_rows) == 1
    assert result.flipped_rows[0]["is_latest"] is False
    assert result.flipped_rows[0]["score_id"] == build.SCORE_LATEST_ID
