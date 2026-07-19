# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""The 5 payload schemas: well-formed, accept conforming payloads, reject drift."""

import json
from pathlib import Path
from typing import Final

import pytest

from contracts.models import Json
from contracts.validation import PAYLOAD_SCHEMAS, check_schema, payload_errors

INVALID_DIR: Final[Path] = Path(__file__).resolve().parent / "data" / "invalid"

_EVIDENCE: Final[dict[str, Json]] = {
    "claim": "8,200 stars in 4 months",
    "source_url": "https://github.com/grasplab/grasp-anything",
    "source_type": "github",
}

_CITED_BULLET: Final[dict[str, Json]] = {
    "text": "Repo reached 8,200 stars in 4 months.",
    "evidence": [_EVIDENCE],
}

_MISSING_BULLET: Final[dict[str, Json]] = {
    "text": "Revenue unknown.",
    "missing": True,
    "gap_field": "traction.revenue",
}

_VALID_SAMPLES: Final[dict[str, dict[str, Json]]] = {
    "evidence": _EVIDENCE,
    "breakdown": {
        "schema_version": 1,
        "categories": {
            "schools": {
                "score": 82,
                "method": "deterministic",
                "rationale": "max tier ETH Zurich",
                "evidence": [_EVIDENCE],
            },
            "traction": {"score": None, "method": "hybrid", "evidence": []},
        },
    },
    "memo": {
        "schema_version": 1,
        "company_snapshot": {"bullets": [_CITED_BULLET]},
        "investment_hypotheses": {"bullets": [_CITED_BULLET]},
        "swot": {"bullets": []},
        "team_and_history": {"bullets": [_CITED_BULLET]},
        "problem_and_product": {"bullets": [_MISSING_BULLET]},
        "technology_and_defensibility": {"bullets": []},
        "market_tam_sam_som": {
            "bullets": [_MISSING_BULLET],
            "tam": "CHF 2B",
            "sam": None,
            "som": None,
            "assumptions": ["robotics grasping TAM proxy"],
        },
        "competition": {"bullets": []},
        "traction_and_kpis": {"bullets": [_CITED_BULLET]},
    },
    "ideal": {
        "schema_version": 1,
        "narrative": "Robotics researcher-founder shipping open-source manipulation stacks.",
        "education": [{"institution": "ETH Zurich", "level": "phd"}],
        "sectors": ["robotics"],
        "numeric_features": {"school_tier": 0.95, "stars_weighted": 0.8},
        "feature_weights": {"school_tier": 1.0},
    },
    "interview": {
        "schema_version": 1,
        "education": [{"institution": "ETH Zurich", "degree": "PhD", "field": "Robotics"}],
        "career": [{"organization": "GraspLab AG", "role": "Founder"}],
        "team_commitment": {"status": "full_time"},
        "traction_claims": [{"metric": "pilot_customers", "value": "3", "verified": False}],
        "funding_status": {"raised_before": False},
    },
}

_INVALID_CASES: Final[tuple[tuple[str, str], ...]] = (
    ("memo", "memo_uncited_bullet.json"),
    ("breakdown", "breakdown_score_out_of_range.json"),
    ("interview", "interview_missing_version.json"),
)


@pytest.mark.parametrize("name", PAYLOAD_SCHEMAS)
def test_schema_is_well_formed(name: str) -> None:
    check_schema(name)


@pytest.mark.parametrize("name", PAYLOAD_SCHEMAS)
def test_valid_sample_passes(name: str) -> None:
    assert payload_errors(name, _VALID_SAMPLES[name]) == []


@pytest.mark.parametrize(("name", "filename"), _INVALID_CASES)
def test_violating_payload_fails(name: str, filename: str) -> None:
    payload: Json = json.loads((INVALID_DIR / filename).read_text(encoding="utf-8"))
    assert payload_errors(name, payload) != []
