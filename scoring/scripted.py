# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Fixture scripts and calibrations: the offline layer that reproduces gold.

Three provenance layers per the WS-E plan:
1. Derived values come from real code and are byte-compared (institution
   seed, ventures/members, pool, gaps, most features).
2. LLM answers are scripted here by TASK tag so `--fixtures --dry-run`
   reproduces gold with zero credentials.
3. Verified fixture drift routes through explicit calibrations
   (`FIXTURE_CALIBRATION`, `FIXTURE_OVERRIDES`): fixture final 78.4 versus
   derived 78.9; schools seeded 92 versus rule 97; Wei stars_weighted 7.9
   versus derived 8.04; recency 0.95/0.9 versus same-day decay ~1.0; seeded
   profile texts. Unit tests assert the true formulas alongside.
"""

import json
from datetime import datetime
from typing import Final

from contracts.models import CategoryScore, Evidence, Json, LLMResponse
from fixtures import build
from scoring.features import FeatureProfile, Overrides
from scoring.stage_a import ScoreCalibration

FIXTURE_NOW: Final[datetime] = datetime.fromisoformat(build.T_UPDATED)
FIXTURE_OLD_NOW: Final[datetime] = datetime.fromisoformat(build.T_OLD_SCORE)
SCORER_MODEL_VERSION: Final[str] = "fixture-scorer-1"
MEMO_MODEL_VERSION: Final[str] = "fixture-memo-1"
OFFLINE_EMBEDDING_MODEL: Final[str] = "fixture-fake-embedding"
SCRIPT_MODEL: Final[str] = "scripted"

# Latest fixture score row: final/confidence are pinned, not derivable
# (sum(w*s) = 78.9, the fixture stores 78.4 / 0.82).
FIXTURE_CALIBRATION: Final[ScoreCalibration] = ScoreCalibration(final_score=78.4, confidence=0.82)
# The pre-interview history row shares identical categories yet differs in
# final/confidence - only reachable through calibration.
FIXTURE_CALIBRATION_OLD: Final[ScoreCalibration] = ScoreCalibration(
    final_score=74.1, confidence=0.7
)

# The exact golden feature key set (gold.person_features fixture rows).
FIXTURE_FEATURE_PROFILE: Final[FeatureProfile] = FeatureProfile(
    keys=("stars_weighted", "commits_12mo", "school_tier", "recency_score", "zero_to_one_flag")
)

# Feature/profile-text calibrations for verified fixture drift.
FIXTURE_OVERRIDES: Final[Overrides] = Overrides(
    feature_values={
        # Fixture recency 0.95; the decay formula gives ~1.0 one day after
        # the last commit.
        build.LENA: {"recency_score": 0.95},
        # Fixture stars_weighted 7.9 (derived log1p(8200*0.38) = 8.04) and
        # recency 0.9 (derived ~0.99).
        build.WEI_A: {"stars_weighted": 7.9, "recency_score": 0.9},
    },
    profile_texts={build.LENA: build.LENA_TEXT, build.WEI_A: build.WEI_A_TEXT},
)

_DEFENSIBILITY_RATIONALE: Final[str] = "Own foundation model, hard-tech stack, permissive license"
_GRASP_REPO_URL: Final[str] = "https://github.com/grasplab/grasp-anything"

# (category, score, method, rationale, evidence source_url) mirroring
# fixtures/build._breakdown - the scripted verdicts behind the golden
# venture_score rows.
_CATEGORY_SEED: Final[tuple[tuple[str, float, str, str, str], ...]] = (
    (
        "individual_experience",
        82.0,
        "sql_features",
        "342 commits in 12mo on an 8,200-star repo",
        _GRASP_REPO_URL,
    ),
    (
        "schools",
        92.0,
        "deterministic",
        "Max tier ETH Zurich (97) across known members",
        "https://api.openalex.org/works/W4400000001",
    ),
    (
        "network_ties",
        60.0,
        "graph",
        "2-hop path to a funded founder via coauthor graph",
        "https://api.openalex.org/works/W4400000001",
    ),
    (
        "prior_collaboration",
        90.0,
        "sql_overlap",
        "Fischer and Zhang share a paper and a repo across 4 months",
        _GRASP_REPO_URL,
    ),
    (
        "problem_realness",
        74.0,
        "web_agent",
        "Recurring complaints about grasping reliability in warehouse automation",
        "https://news.ycombinator.com/item?id=fixture",
    ),
    ("product_defensibility", 80.0, "ai_query", _DEFENSIBILITY_RATIONALE, _GRASP_REPO_URL),
    (
        "market",
        68.0,
        "web_agent",
        "Robotic manipulation TAM growing with named competitors",
        "https://example.com/market-report",
    ),
    (
        "traction",
        71.0,
        "hybrid",
        "8,200 stars in 4 months; revenue unknown pending interview",
        _GRASP_REPO_URL,
    ),
    (
        "ideal_match",
        84.0,
        "structured_match",
        "Education 92, domain-fit 0.91, stars p95",
        "https://grasplab.ch",
    ),
)


def fixture_category_results() -> dict[str, CategoryScore]:
    """The nine scripted category verdicts matching the fixture breakdown.

    Returns:
        CategoryScores keyed by category name.
    """
    return {
        name: CategoryScore(
            category=name,
            score=score,
            confidence=0.8,
            method=method,
            rationale=rationale,
            evidence=(
                Evidence(
                    claim=rationale,
                    source_url=url,
                    source_type="fixture",
                    snippet=None,
                    weight=None,
                ),
            ),
        )
        for name, score, method, rationale, url in _CATEGORY_SEED
    }


def _cited(text: str, url: str) -> dict[str, Json]:
    return {
        "text": text,
        "evidence": [{"claim": text, "source_url": url, "source_type": "fixture"}],
    }


def _missing(text: str, gap_field: str) -> dict[str, Json]:
    return {"text": text, "missing": True, "gap_field": gap_field}


def fixture_memo_sections() -> dict[str, Json]:
    """The scripted memo sections (mirror of fixtures/build._memo_sections).

    Returns:
        The nine-section memo payload.
    """
    return {
        "schema_version": 1,
        "company_snapshot": {
            "bullets": [
                _cited(
                    "GraspLab AG incorporated in Zurich on 2026-06-20.",
                    "https://www.zefix.admin.ch/api/v1/company/uid/CHE-123.456.789",
                )
            ]
        },
        "investment_hypotheses": {
            "bullets": [
                _cited(
                    "Grasping foundation models are becoming the default robotics stack.",
                    "https://arxiv.org/abs/2506.11111",
                )
            ]
        },
        "swot": {
            "bullets": [
                _cited(
                    "Strength: 8,200-star open-source traction in 4 months.",
                    _GRASP_REPO_URL,
                )
            ]
        },
        "team_and_history": {
            "bullets": [
                _cited(
                    "Founder Lena Fischer links GitHub, arXiv, and the Zefix registry.",
                    "https://api.openalex.org/works/W4400000001",
                )
            ]
        },
        "problem_and_product": {
            "bullets": [
                _cited(
                    "GraspFM targets unreliable grasping in warehouse automation.",
                    "https://arxiv.org/abs/2506.11111",
                )
            ]
        },
        "technology_and_defensibility": {
            "bullets": [
                _cited(
                    "Own foundation model with published research, not an API wrapper.",
                    "https://arxiv.org/abs/2506.11111",
                )
            ]
        },
        "market_tam_sam_som": {
            "bullets": [_missing("Bottom-up market sizing not yet computed.", "market.tam")],
            "tam": None,
            "sam": None,
            "som": None,
            "assumptions": [],
        },
        "competition": {
            "bullets": [
                _cited(
                    "Competes with in-house grasping stacks at large robotics vendors.",
                    "https://example.com/market-report",
                )
            ]
        },
        "traction_and_kpis": {
            "bullets": [
                _cited("8,200 GitHub stars, 410 forks.", _GRASP_REPO_URL),
                _missing("Revenue and pilot count unknown.", "traction.revenue"),
            ]
        },
    }


def _response(parsed: dict[str, Json]) -> LLMResponse:
    return LLMResponse(text=json.dumps(parsed, sort_keys=True), parsed=parsed, model=SCRIPT_MODEL)


def fixture_scripts() -> dict[str, LLMResponse]:
    """Every scripted TASK-tag response the offline pipeline needs.

    Returns:
        Responses keyed by prompt tag (the prompt's first line).
    """
    venture = build.GRASP_VENTURE
    scripts: dict[str, LLMResponse] = {
        f"TASK:venture_summary venture={venture}": LLMResponse(
            text="ETH spin-off shipping open-source grasping foundation models.",
            parsed=None,
            model=SCRIPT_MODEL,
        ),
        f"TASK:memo venture={venture}": _response(fixture_memo_sections()),
        f"TASK:product_defensibility venture={venture}": _response(
            {
                "score": 80.0,
                "confidence": 0.8,
                "rationale": _DEFENSIBILITY_RATIONALE,
                "evidence": [
                    {
                        "claim": _DEFENSIBILITY_RATIONALE,
                        "source_url": _GRASP_REPO_URL,
                        "source_type": "fixture",
                    }
                ],
            }
        ),
        f"TASK:funding_confirm venture={venture}": _response(
            {"verdict": "none_found", "rationale": "No funding vocabulary applies to the venture."}
        ),
    }
    for person_id, quality, fit in ((build.LENA, 85.0, 90.0), (build.WEI_A, 75.0, 70.0)):
        scripts[f"TASK:commit_quality person={person_id}"] = _response(
            {"score": quality, "rationale": "Coherent scope with tests on sampled commits."}
        )
        scripts[f"TASK:experience_fit person={person_id}"] = _response(
            {"score": fit, "rationale": "Research history matches the venture problem."}
        )
    return scripts
