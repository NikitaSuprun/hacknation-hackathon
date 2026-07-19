# Copyright (c) 2026 Venture Hunt. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Person features: golden bytes under calibration; real formulas unit-tested.

Documented divergences (calibrated in scoring.scripted.FIXTURE_OVERRIDES,
asserted here with the true derivations):
- Wei stars_weighted: fixture 7.9, derived log1p(8200*0.38) = 8.04.
- recency_score: fixture 0.95/0.9, derived ~1.0 one day after the last commit.
"""

import math

from fixtures import build
from scoring import scripted
from scoring.deps import ScoringDeps
from scoring.features import NO_OVERRIDES, FeatureRequest, build_person_features
from scoring.institution_seed import build_institution_rows
from scoring.institutions import SeededInstitutionScorer
from scoring.serialize import to_jsonl_lines
from scoring.snapshot import GoldInputs, SilverSnapshot
from tests.scoring.conftest import MEMBER_IDS, golden_text


def request(silver: SilverSnapshot, deps: ScoringDeps, *, calibrated: bool) -> FeatureRequest:
    scorer = SeededInstitutionScorer(
        list(build_institution_rows(now=scripted.FIXTURE_NOW)), deps.log
    )
    return FeatureRequest(
        person_ids=MEMBER_IDS,
        snapshot=silver,
        institutions=scorer,
        llm=deps.llm,
        clock=deps.clock,
        profile=scripted.FIXTURE_FEATURE_PROFILE,
        overrides=scripted.FIXTURE_OVERRIDES if calibrated else NO_OVERRIDES,
        embedding_model=scripted.OFFLINE_EMBEDDING_MODEL,
    )


def features_of(
    silver: SilverSnapshot, deps: ScoringDeps, *, calibrated: bool
) -> dict[str, dict[str, float]]:
    rows = build_person_features(request(silver, deps, calibrated=calibrated))
    out: dict[str, dict[str, float]] = {}
    for row in rows:
        cell = row["features"]
        assert isinstance(cell, dict)
        person_id = row["person_id"]
        assert isinstance(person_id, str)
        out[person_id] = {key: value for key, value in cell.items() if isinstance(value, float)}
    return out


def test_feature_rows_byte_reproduce_golden_file(silver: SilverSnapshot, deps: ScoringDeps) -> None:
    rows = build_person_features(request(silver, deps, calibrated=True))
    assert to_jsonl_lines(rows) == golden_text("gold.person_features")


def test_real_derivations_without_calibration(silver: SilverSnapshot, deps: ScoringDeps) -> None:
    derived = features_of(silver, deps, calibrated=False)
    lena, wei = derived[build.LENA], derived[build.WEI_A]
    assert lena["stars_weighted"] == round(math.log1p(8200 * 0.62), 2)  # 8.53, as pinned
    assert wei["stars_weighted"] == round(math.log1p(8200 * 0.38), 2)  # 8.04, fixture pins 7.9
    assert wei["stars_weighted"] == 8.04
    assert lena["commits_12mo"] == 342.0
    assert wei["commits_12mo"] == 208.0
    assert lena["school_tier"] == 0.97
    assert wei["school_tier"] == 0.97
    # Commits landed 1-2 days before the frozen clock: the decay formula
    # gives ~1.0; the fixture pins 0.95/0.9 (calibration seam).
    assert lena["recency_score"] == 1.0
    assert wei["recency_score"] == 0.99


def test_zero_to_one_flag_fires_for_lena_only(silver: SilverSnapshot, deps: ScoringDeps) -> None:
    derived = features_of(silver, deps, calibrated=False)
    assert derived[build.LENA]["zero_to_one_flag"] == 1.0
    assert "zero_to_one_flag" not in derived[build.WEI_A]  # NULL = absent, never zero


def test_calibration_overrides_apply_only_where_verified(
    silver: SilverSnapshot, deps: ScoringDeps
) -> None:
    calibrated = features_of(silver, deps, calibrated=True)
    assert calibrated[build.WEI_A]["stars_weighted"] == 7.9
    assert calibrated[build.LENA]["stars_weighted"] == 8.53  # untouched, formula value
    assert calibrated[build.LENA]["recency_score"] == 0.95
    assert calibrated[build.WEI_A]["recency_score"] == 0.9


def test_profile_texts_and_embeddings_are_the_seeded_pair(
    silver: SilverSnapshot, deps: ScoringDeps
) -> None:
    rows = build_person_features(request(silver, deps, calibrated=True))
    texts = {row["person_id"]: row["profile_text"] for row in rows}
    assert texts[build.LENA] == build.LENA_TEXT
    assert texts[build.WEI_A] == build.WEI_A_TEXT
    embedding = rows[0]["profile_embedding"]
    assert isinstance(embedding, list)
    assert len(embedding) == 1024


def test_emitted_keys_follow_the_profile(
    silver: SilverSnapshot, deps: ScoringDeps, gold: GoldInputs
) -> None:
    derived = features_of(silver, deps, calibrated=True)
    golden_features = {str(row["person_id"]): row["features"] for row in gold.features}
    for person_id, cell in derived.items():
        golden_cell = golden_features[person_id]
        assert isinstance(golden_cell, dict)
        assert set(cell) == set(golden_cell)
