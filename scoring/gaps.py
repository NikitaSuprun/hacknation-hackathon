# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""gold.venture_gaps: unfilled fields ranked into the interview question plan.

The catalog owns the exact question wording (the outreach flow reuses it
verbatim); ranking is VC-weight times field importance, capped at the top
eight so the interview stays short.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Final

from contracts.models import SinkRow
from scoring.categories.base import weight_column
from scoring.snapshot import Row, get_float

MAX_GAPS: Final[int] = 8


@dataclass(frozen=True, slots=True)
class GapSpec:
    """One catalog entry: the field, its category, and the interview question."""

    field: str
    category: str
    question_text: str
    importance: float


GAP_CATALOG: Final[tuple[GapSpec, ...]] = (
    GapSpec(
        field="traction.revenue",
        category="traction",
        question_text="Do you have paying pilots or revenue today?",
        importance=0.9,
    ),
    GapSpec(
        field="market.tam",
        category="market",
        question_text="Which customer segment do you serve first, and how large is it?",
        importance=0.7,
    ),
)


def build_gaps(
    venture_id: str,
    weights_row: Row,
    filled: frozenset[str],
    now: datetime,
) -> list[SinkRow]:
    """Rank the venture's unfilled fields into gap rows.

    Args:
        venture_id: The venture to plan questions for.
        weights_row: The gold.score_weights row (w_i x importance ranking).
        filled: Fields already answered (interview or verified data).
        now: The created_at timestamp.

    Returns:
        Up to MAX_GAPS rows, highest-rank first.
    """
    open_specs = [spec for spec in GAP_CATALOG if spec.field not in filled]

    def rank(spec: GapSpec) -> float:
        weight = get_float(weights_row, weight_column(spec.category)) or 0.0
        return weight * spec.importance

    open_specs.sort(key=rank, reverse=True)
    return [
        {
            "venture_id": venture_id,
            "field": spec.field,
            "category": spec.category,
            "question_text": spec.question_text,
            "importance": spec.importance,
            "created_at": now,
        }
        for spec in open_specs[:MAX_GAPS]
    ]
