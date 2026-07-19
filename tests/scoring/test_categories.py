# Copyright (c) 2026 Venture Hunt. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Category math: real rubric formulas, renormalization, payload shapes.

Documented divergence: the schools rule computes 97.0 on the fixture data
(both members ETH tier 0.97) while the seeded fixture breakdown pins 92.0 —
the golden path uses scripted verdicts, the formula is asserted here.
"""

from typing import Final

from contracts.models import CategoryScore, Evidence, FeatureBundle, VentureView
from fixtures import build
from scoring import scripted
from scoring.categories.base import (
    CATEGORY_NAMES,
    category_payload,
    diversity,
    renormalized_weights,
    run_confidence,
    weighted_final,
)
from scoring.categories.scorers import (
    IdealMatchScorer,
    IndividualExperienceScorer,
    PriorCollaborationScorer,
    SchoolsScorer,
    percentile,
)
from scoring.categories.stage_b import stage_b_registry
from scoring.snapshot import GoldInputs, Row


def venture(members: tuple[str, ...], extras: dict[str, object]) -> VentureView:
    typed_extras = {
        key: value for key, value in extras.items() if isinstance(value, int | float | str | bool)
    }
    return VentureView(
        venture_id=build.GRASP_VENTURE,
        name="GraspLab",
        one_liner="Foundation models for robotic grasping",
        anchor_type="repo",
        member_person_ids=members,
        extras=typed_extras,
    )


def bundle(person_features: dict[str, dict[str, float]]) -> FeatureBundle:
    return FeatureBundle(person_features=person_features, venture_features={})


FIXTURE_FEATURES: Final[dict[str, dict[str, float]]] = {
    build.LENA: {
        "stars_weighted": 8.53,
        "commits_12mo": 342.0,
        "school_tier": 0.97,
        "recency_score": 0.95,
        "zero_to_one_flag": 1.0,
    },
    build.WEI_A: {
        "stars_weighted": 7.9,
        "commits_12mo": 208.0,
        "school_tier": 0.97,
        "recency_score": 0.9,
    },
}


def test_schools_rule_gives_97_on_fixture_data() -> None:
    verdict = SchoolsScorer().score(
        venture((build.LENA, build.WEI_A), {}), bundle(FIXTURE_FEATURES)
    )
    assert verdict.score == 97.0  # fixture pins 92.0; divergence documented above


def test_schools_without_tiers_is_not_applicable() -> None:
    verdict = SchoolsScorer().score(
        venture((build.LENA,), {}), bundle({build.LENA: {"commits_12mo": 10.0}})
    )
    assert verdict.score is None


def test_prior_collaboration_ladder() -> None:
    scorer = PriorCollaborationScorer()
    two = (build.LENA, build.WEI_A)
    strong = scorer.score(venture(two, {"collab_contexts": 2, "collab_years": 0.3}), bundle({}))
    assert strong.score == 90.0
    years = scorer.score(venture(two, {"collab_contexts": 1, "collab_years": 2.5}), bundle({}))
    assert years.score == 90.0
    single = scorer.score(venture(two, {"collab_contexts": 1, "collab_years": 0.3}), bundle({}))
    assert single.score == 65.0
    current = scorer.score(venture(two, {"collab_contexts": 0, "collab_years": 0.0}), bundle({}))
    assert current.score == 30.0
    solo = scorer.score(venture((build.LENA,), {"collab_contexts": 0}), bundle({}))
    assert solo.score is None  # weight gets redistributed, never a silent 50


def test_percentile_is_fraction_at_or_below() -> None:
    assert percentile(8.53, [8.53, 7.9]) == 1.0
    assert percentile(7.9, [8.53, 7.9]) == 0.5
    assert percentile(1.0, []) == 1.0


def test_individual_experience_prefers_the_stronger_member() -> None:
    scorer = IndividualExperienceScorer(FIXTURE_FEATURES)
    both = scorer.score(venture((build.LENA, build.WEI_A), {}), bundle(FIXTURE_FEATURES))
    wei_only = scorer.score(venture((build.WEI_A,), {}), bundle(FIXTURE_FEATURES))
    assert both.score is not None
    assert wei_only.score is not None
    assert both.score > wei_only.score  # Lena's 0->1 flag and percentiles dominate


def test_ideal_match_is_directional_meets_or_exceeds(gold: GoldInputs) -> None:
    ideal_row: Row = gold.ideals[0]
    profile = ideal_row.get("profile_json")
    assert isinstance(profile, dict)
    embedding = [0.0] * 1024
    scorer = IdealMatchScorer(profile, embedding, {})
    exceeding = scorer.score(venture((build.LENA,), {}), bundle(FIXTURE_FEATURES))
    assert exceeding.score == 100.0  # every feature meets or exceeds the ideal point
    weaker = scorer.score(
        venture((build.WEI_A,), {}),
        bundle({build.WEI_A: {"school_tier": 0.475, "stars_weighted": 4.0, "recency_score": 0.45}}),
    )
    assert weaker.score is not None
    assert weaker.score < 60.0


def test_renormalized_weights_redistribute_na_pro_rata(gold: GoldInputs) -> None:
    weights_row = gold.weights[0]
    full = renormalized_weights(weights_row, CATEGORY_NAMES)
    assert round(sum(full.values()), 6) == 1.0
    without_collab = renormalized_weights(
        weights_row, [name for name in CATEGORY_NAMES if name != "prior_collaboration"]
    )
    assert "prior_collaboration" not in without_collab
    assert round(sum(without_collab.values()), 6) == 1.0
    assert without_collab["schools"] > full["schools"]


def test_weighted_final_over_fixture_verdicts_is_78_9(gold: GoldInputs) -> None:
    categories = scripted.fixture_category_results()
    weights = renormalized_weights(gold.weights[0], CATEGORY_NAMES)
    # The true weighted sum; the fixture pins 78.4 via ScoreCalibration.
    assert weighted_final(weights, categories) == 78.9


def test_run_confidence_drops_with_coverage(gold: GoldInputs) -> None:
    categories = scripted.fixture_category_results()
    full = run_confidence(gold.weights[0], categories, {})
    partial = run_confidence(gold.weights[0], categories, {"schools": 0.5})
    assert 0.0 < partial < full <= 1.0


def test_diversity_factor_tiers() -> None:
    def evidence(*source_types: str) -> tuple[Evidence, ...]:
        return tuple(
            Evidence(claim="c", source_url="https://x", source_type=kind, snippet=None, weight=None)
            for kind in source_types
        )

    assert diversity(evidence("github", "zefix")) == 1.0
    assert diversity(evidence("github")) == 0.8
    assert diversity(()) == 0.5


def test_category_payload_omits_none_evidence_fields() -> None:
    verdict = CategoryScore(
        category="schools",
        score=97.0,
        confidence=0.8,
        method="deterministic",
        rationale="max tier",
        evidence=(
            Evidence(
                claim="c", source_url="https://x", source_type="fixture", snippet=None, weight=None
            ),
        ),
    )
    payload = category_payload(verdict)
    evidence = payload["evidence"]
    assert isinstance(evidence, list)
    first = evidence[0]
    assert isinstance(first, dict)
    assert set(first) == {"claim", "source_url", "source_type"}


def test_stage_b_registry_delegates_and_defaults() -> None:
    results = {"market": scripted.fixture_category_results()["market"]}
    registry = stage_b_registry(results)
    view = venture((build.LENA,), {})
    empty = bundle({})
    assert registry["market"].score(view, empty).score == 68.0
    missing = registry["traction"].score(view, empty)
    assert missing.score is None
    assert missing.method == "web_agent"
