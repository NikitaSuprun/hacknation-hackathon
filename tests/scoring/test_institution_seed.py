# Copyright (c) 2026 Venture Hunt. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Institution seed: golden bytes, MIT>KTH, aliases, unknown floors, 50/50 blend."""

from scoring.deps import ScoringDeps
from scoring.institution_seed import (
    COMPANY_SEED,
    UNIVERSITY_SEED,
    blended_score,
    build_institution_rows,
)
from scoring.institutions import (
    UNKNOWN_COMPANY_SCORE,
    UNKNOWN_UNIVERSITY_SCORE,
    SeededInstitutionScorer,
)
from scoring.scripted import FIXTURE_NOW
from scoring.serialize import to_jsonl_lines
from tests.scoring.conftest import golden_text


def rows_scorer(deps: ScoringDeps) -> SeededInstitutionScorer:
    return SeededInstitutionScorer(list(build_institution_rows(now=FIXTURE_NOW)), deps.log)


def test_institution_rows_byte_reproduce_golden_file() -> None:
    rows = build_institution_rows(now=FIXTURE_NOW)
    assert to_jsonl_lines(rows) == golden_text("gold.institution_score")


def test_every_seed_score_is_the_5050_blend() -> None:
    for _, prestige, outcome, score in (*UNIVERSITY_SEED, *COMPANY_SEED):
        assert blended_score(prestige, outcome) == score


def test_mit_outranks_kth(deps: ScoringDeps) -> None:
    scorer = rows_scorer(deps)
    mit = scorer.score("MIT", "university")
    kth = scorer.score("KTH Royal Institute of Technology", "university")
    assert mit.score == 100.0
    assert kth.score == 82.0
    assert mit.score > kth.score


def test_alias_spellings_resolve_to_the_same_row(deps: ScoringDeps) -> None:
    scorer = rows_scorer(deps)
    canonical = scorer.score("ETH Zurich", "university")
    for spelling in ("ETH Zürich", "ethz", "Eidgenössische Technische Hochschule Zürich"):
        resolved = scorer.score(spelling, "university")
        assert resolved.institution_id == canonical.institution_id
        assert resolved.score == 97.0


def test_company_aliases_resolve(deps: ScoringDeps) -> None:
    scorer = rows_scorer(deps)
    assert scorer.score("Klarna", "company").score == 85.0
    assert scorer.score("google", "company").score == 98.0


def test_unknown_institutions_get_floor_with_none_components(deps: ScoringDeps) -> None:
    scorer = rows_scorer(deps)
    university = scorer.score("Obscure Polytechnic of Nowhere", "university")
    assert university.score == UNKNOWN_UNIVERSITY_SCORE
    assert university.prestige is None
    assert university.outcome is None
    company = scorer.score("Tiny Unknown GmbH", "company")
    assert company.score == UNKNOWN_COMPANY_SCORE
    assert company.prestige is None


def test_kind_mismatch_is_a_miss(deps: ScoringDeps) -> None:
    scorer = rows_scorer(deps)
    assert scorer.score("ETH Zurich", "company").score == UNKNOWN_COMPANY_SCORE
