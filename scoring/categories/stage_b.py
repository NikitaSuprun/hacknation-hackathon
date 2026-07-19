# Copyright (c) 2026 Venture Hunt. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Stage-B category scorers: thin delegates over precomputed deep-dive results.

The web-search agent (scoring.deepdive) runs once per venture and produces
verdicts for 2.1 / 2.3 / 2.4 / 1.1.3; these scorers slot those verdicts into
the same registry shape Stage A uses, so run_stage_a stays a pure function.
"""

from collections.abc import Mapping
from typing import Final

from contracts.interfaces import CategoryScorer
from contracts.models import CategoryScore, FeatureBundle, VentureView

STAGE_B_CATEGORIES: Final[tuple[str, ...]] = (
    "problem_realness",
    "market",
    "traction",
    "network_ties",
)

type DeepDiveResults = Mapping[str, CategoryScore]
"""Deep-dive verdicts keyed by category name."""


class DeepDiveResultScorer:
    """CategoryScorer serving one category out of a deep-dive result mapping."""

    def __init__(self, category: str, results: DeepDiveResults) -> None:
        """Bind the category and the precomputed results."""
        self.category: str = category
        self._results: Final[DeepDiveResults] = results

    def score(self, venture: VentureView, features: FeatureBundle) -> CategoryScore:
        """Return the precomputed verdict for this category.

        Args:
            venture: Unused (verdicts are precomputed per venture).
            features: Unused.

        Returns:
            The deep-dive verdict, or a no-evidence N/A when absent.
        """
        del venture, features
        found = self._results.get(self.category)
        if found is not None:
            return found
        return CategoryScore(
            category=self.category,
            score=None,
            confidence=0.2,
            method="web_agent",
            rationale="no deep-dive result available",
            evidence=(),
        )


def stage_b_registry(results: DeepDiveResults) -> dict[str, CategoryScorer]:
    """Registry slice for the four deep-dive categories.

    Args:
        results: Deep-dive verdicts keyed by category.

    Returns:
        One delegate scorer per Stage-B category.
    """
    return {name: DeepDiveResultScorer(name, results) for name in STAGE_B_CATEGORIES}
