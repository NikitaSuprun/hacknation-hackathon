# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Shared category machinery: names, payloads, weights, confidence.

The breakdown payload here must satisfy contracts/schemas/breakdown.schema.json
and byte-match the fixture rendering: evidence elements omit None-valued
optional fields, category payloads always carry the five keys.
"""

from collections.abc import Iterable, Mapping
from typing import Final

from contracts.interfaces import CategoryScorer
from contracts.models import CategoryScore, Evidence, Json
from scoring.snapshot import Row, get_float

CATEGORY_NAMES: Final[tuple[str, ...]] = (
    "individual_experience",
    "schools",
    "network_ties",
    "prior_collaboration",
    "problem_realness",
    "product_defensibility",
    "market",
    "traction",
    "ideal_match",
)
SCHEMA_VERSION: Final[int] = 1

MULTI_SOURCE_MIN: Final[int] = 2
DIVERSITY_MULTI_SOURCE: Final[float] = 1.0
DIVERSITY_SINGLE_SOURCE: Final[float] = 0.8
DIVERSITY_INFERENCE_ONLY: Final[float] = 0.5

VENTURE_MEAN_WEIGHT: Final[float] = 0.6
VENTURE_MAX_WEIGHT: Final[float] = 0.4


def weight_column(category: str) -> str:
    """The gold.score_weights column for one category.

    Args:
        category: The category name.

    Returns:
        The `w_<category>` column name.
    """
    return f"w_{category}"


def evidence_payload(evidence: Evidence) -> dict[str, Json]:
    """Render one evidence element, omitting None-valued optional fields.

    Args:
        evidence: The evidence value object.

    Returns:
        The JSON payload ({claim, source_url} plus set optionals).
    """
    payload: dict[str, Json] = {"claim": evidence.claim, "source_url": evidence.source_url}
    if evidence.source_type is not None:
        payload["source_type"] = evidence.source_type
    if evidence.snippet is not None:
        payload["snippet"] = evidence.snippet
    if evidence.weight is not None:
        payload["weight"] = evidence.weight
    return payload


def category_payload(score: CategoryScore) -> dict[str, Json]:
    """Render one category verdict for the breakdown VARIANT.

    Args:
        score: The category verdict.

    Returns:
        The JSON payload with score/method/rationale/confidence/evidence.
    """
    return {
        "score": score.score,
        "method": score.method,
        "rationale": score.rationale,
        "confidence": score.confidence,
        "evidence": [evidence_payload(item) for item in score.evidence],
    }


def breakdown_payload(categories: Mapping[str, CategoryScore]) -> dict[str, Json]:
    """Assemble the full breakdown payload in rubric order.

    Args:
        categories: Category verdicts keyed by name.

    Returns:
        The `{schema_version, categories}` payload.
    """
    ordered: dict[str, Json] = {
        name: category_payload(categories[name]) for name in CATEGORY_NAMES if name in categories
    }
    return {"schema_version": SCHEMA_VERSION, "categories": ordered}


def renormalized_weights(weights_row: Row, available: Iterable[str]) -> dict[str, float]:
    """VC weights renormalized over the available categories.

    An N/A category redistributes its weight pro-rata — never a silent 50.

    Args:
        weights_row: The gold.score_weights row.
        available: Categories that produced a usable score.

    Returns:
        Weights over the available categories summing to 1 (empty when none).
    """
    raw = {
        name: get_float(weights_row, weight_column(name)) or 0.0
        for name in CATEGORY_NAMES
        if name in set(available)
    }
    total = sum(raw.values())
    if total <= 0.0:
        return {}
    return {name: value / total for name, value in raw.items()}


def weighted_final(weights: Mapping[str, float], categories: Mapping[str, CategoryScore]) -> float:
    """The precomputed final score: renormalized-weighted category sum.

    Args:
        weights: Renormalized weights over scored categories.
        categories: Category verdicts keyed by name.

    Returns:
        The 0..100 final score, rounded to one decimal.
    """
    total = 0.0
    for name, weight in weights.items():
        score = categories[name].score
        if score is not None:
            total += weight * score
    return round(total, 1)


def diversity(evidence: tuple[Evidence, ...]) -> float:
    """Evidence-source diversity factor for confidence.

    Args:
        evidence: The category's evidence tuple.

    Returns:
        1.0 for two or more source types, 0.8 for one, 0.5 for none.
    """
    kinds = {item.source_type for item in evidence if item.source_type is not None}
    if len(kinds) >= MULTI_SOURCE_MIN:
        return DIVERSITY_MULTI_SOURCE
    if len(kinds) == 1:
        return DIVERSITY_SINGLE_SOURCE
    return DIVERSITY_INFERENCE_ONLY


def run_confidence(
    weights_row: Row,
    categories: Mapping[str, CategoryScore],
    coverage: Mapping[str, float],
) -> float:
    """Data-coverage confidence: sum of w_i * coverage_i * diversity_i.

    Weighted by the VC's own weights so confidence drops where the VC cares;
    categories with no verdict contribute zero.

    Args:
        weights_row: The gold.score_weights row (raw, all nine categories).
        categories: Category verdicts keyed by name.
        coverage: 0..1 filled/required per category (absent means 1.0).

    Returns:
        The 0..1 confidence, rounded to two decimals.
    """
    raw = {name: get_float(weights_row, weight_column(name)) or 0.0 for name in CATEGORY_NAMES}
    total_weight = sum(raw.values())
    if total_weight <= 0.0:
        return 0.0
    value = 0.0
    for name, weight in raw.items():
        verdict = categories.get(name)
        if verdict is None or verdict.score is None:
            continue
        value += weight * coverage.get(name, 1.0) * diversity(verdict.evidence)
    return round(value / total_weight, 2)


class ScriptedCategoryScorer:
    """A CategoryScorer returning one fixed verdict (fixtures and tests)."""

    def __init__(self, result: CategoryScore) -> None:
        """Bind the verdict; the category comes from the result itself."""
        self.category: str = result.category
        self._result: Final[CategoryScore] = result

    def score(self, venture: object, features: object) -> CategoryScore:
        """Return the scripted verdict.

        Args:
            venture: Ignored.
            features: Ignored.

        Returns:
            The bound verdict.
        """
        del venture, features
        return self._result


def scripted_registry(results: Mapping[str, CategoryScore]) -> dict[str, CategoryScorer]:
    """Build a registry of scripted scorers from literal verdicts.

    Args:
        results: Category verdicts keyed by name.

    Returns:
        A registry usable wherever real scorers are.
    """
    return {name: ScriptedCategoryScorer(result) for name, result in results.items()}
