# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""The calibrated gold.institution_score seed (home of MIT > KTH).

Mirrors the fixture constants in fixtures/build._institution_scores: ROR ids,
canonical names, and aliases come from the CC0 resolver seed; only the
calibration numbers are owned here. Every score satisfies the blend
`score = round(50*prestige + 50*outcome, 1)` — a unit-tested invariant.
"""

from datetime import datetime
from typing import Final

from contracts.models import SinkRow, SinkValue
from tools import ids, institutions, norm
from tools.institutions import InstitutionRecord

SEED_NAME: Final[str] = "ws0-fixture"
UNIVERSITY_SOURCES: Final[tuple[str, str, str]] = ("ror-cc0", "leiden-open-cc0", "hand-curated")
COMPANY_SOURCES: Final[tuple[str]] = ("hand-curated",)

# (resolver query, prestige, outcome, blended score)
UNIVERSITY_SEED: Final[tuple[tuple[str, float, float, float], ...]] = (
    ("Massachusetts Institute of Technology", 1.00, 1.00, 100.0),
    ("ETH Zurich", 0.95, 0.99, 97.0),
    ("Stanford University", 1.00, 1.00, 100.0),
    ("EPFL", 0.90, 0.96, 93.0),
    ("KTH", 0.82, 0.82, 82.0),
    ("University of Zurich", 0.75, 0.75, 75.0),
)

# (canonical name, prestige tier, outcome, blended score)
COMPANY_SEED: Final[tuple[tuple[str, float, float, float], ...]] = (
    ("GOOGLE", 0.98, 0.98, 98.0),
    ("ANTHROPIC", 0.97, 0.95, 96.0),
    ("KLARNA", 0.80, 0.90, 85.0),
    ("ABB", 0.55, 0.45, 50.0),
)


class UnseededInstitutionError(LookupError):
    """Raised when a seeded university is absent from the ROR resolver data."""

    def __init__(self, query: str) -> None:
        """Name the unresolved institution."""
        super().__init__(f"{query} does not resolve; extend data/institutions/seed_queries.txt")


def blended_score(prestige: float, outcome: float) -> float:
    """The university/company blend: 50 points prestige, 50 points outcome.

    Args:
        prestige: 0..1 prestige component.
        outcome: 0..1 founder-production component.

    Returns:
        The 0..100 blended score, rounded to one decimal.
    """
    return round(50.0 * prestige + 50.0 * outcome, 1)


def _resolved(query: str) -> InstitutionRecord:
    record = institutions.resolve(query)
    if record is None:
        raise UnseededInstitutionError(query)
    return record


def _university_row(
    record: InstitutionRecord, prestige: float, outcome: float, score: float, now: datetime
) -> SinkRow:
    alias_keys = sorted({norm.org_key(a) for a in (record.name, *record.aliases)} - {""})
    aliases: SinkValue = list(alias_keys)
    return {
        "institution_id": ids.institution_id(record.ror_id),
        "kind": "university",
        "canonical_name": record.name,
        "aliases": aliases,
        "ror_id": record.ror_id,
        "prestige": prestige,
        "outcome": outcome,
        "score": score,
        "provenance": {"seed": SEED_NAME, "sources": list(UNIVERSITY_SOURCES)},
        "updated_at": now,
    }


def _company_row(
    name: str, prestige: float, outcome: float, score: float, now: datetime
) -> SinkRow:
    return {
        "institution_id": ids.institution_id(name),
        "kind": "company",
        "canonical_name": name,
        "aliases": [norm.org_key(name)],
        "ror_id": None,
        "prestige": prestige,
        "outcome": outcome,
        "score": score,
        "provenance": {"seed": SEED_NAME, "sources": list(COMPANY_SOURCES)},
        "updated_at": now,
    }


def build_institution_rows(*, now: datetime) -> list[SinkRow]:
    """Build every seed row for gold.institution_score.

    A university query outside the ROR resolver seed raises
    UnseededInstitutionError (from the resolution helper).

    Args:
        now: The updated_at timestamp (injected clock).

    Returns:
        University rows then company rows, in seed order.
    """
    rows: list[SinkRow] = []
    for query, prestige, outcome, score in UNIVERSITY_SEED:
        rows.append(_university_row(_resolved(query), prestige, outcome, score, now))
    for name, prestige, outcome, score in COMPANY_SEED:
        rows.append(_company_row(name, prestige, outcome, score, now))
    return rows
