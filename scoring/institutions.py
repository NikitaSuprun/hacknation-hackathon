# Copyright (c) 2026 Venture Hunt. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""InstitutionScorer over the calibrated gold.institution_score rows.

Lookup is alias-first (the seed rows carry org_key'd aliases), then via the
ROR resolver for spellings the seed has not listed. Unknown organisations get
the documented floor (35 university / 30 company) with prestige/outcome None
so downstream features can tell "unknown" from "known but weak" — and the
miss is logged, never silent.
"""

from collections.abc import Mapping, Sequence
from typing import Final, Literal, cast

from structlog.typing import FilteringBoundLogger

from contracts.models import InstitutionScore
from tools import ids, institutions
from tools.norm import org_key

UNKNOWN_UNIVERSITY_SCORE: Final[float] = 35.0
UNKNOWN_COMPANY_SCORE: Final[float] = 30.0

type Kind = Literal["university", "company"]


def _row_str(row: Mapping[str, object], key: str) -> str | None:
    value = row.get(key)
    return value if isinstance(value, str) else None


def _row_float(row: Mapping[str, object], key: str) -> float | None:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _row_aliases(row: Mapping[str, object]) -> list[str]:
    value = row.get("aliases")
    if not isinstance(value, list):
        return []
    items = cast("list[object]", value)
    return [item for item in items if isinstance(item, str)]


def _as_score(row: Mapping[str, object]) -> InstitutionScore | None:
    institution_id = _row_str(row, "institution_id")
    kind = _row_str(row, "kind")
    name = _row_str(row, "canonical_name")
    score = _row_float(row, "score")
    if institution_id is None or kind is None or name is None or score is None:
        return None
    return InstitutionScore(
        institution_id=institution_id,
        kind=kind,
        canonical_name=name,
        score=score,
        prestige=_row_float(row, "prestige"),
        outcome=_row_float(row, "outcome"),
    )


class SeededInstitutionScorer:
    """Resolve raw institution names against the calibrated seed rows."""

    def __init__(self, rows: Sequence[Mapping[str, object]], log: FilteringBoundLogger) -> None:
        """Index the seed rows by their alias keys, per kind."""
        self._index: Final[dict[tuple[str, str], InstitutionScore]] = {}
        self._log: Final[FilteringBoundLogger] = log
        for row in rows:
            record = _as_score(row)
            if record is None:
                continue
            keys = {org_key(record.canonical_name), *_row_aliases(row)}
            for key in keys:
                if key:
                    self._index.setdefault((record.kind, key), record)

    def _lookup(self, name: str, kind: Kind) -> InstitutionScore | None:
        direct = self._index.get((kind, org_key(name)))
        if direct is not None:
            return direct
        return self._index.get((kind, institutions.org_norm(name)))

    def score(self, name: str, kind: Literal["university", "company"]) -> InstitutionScore:
        """Resolve a raw institution name to its calibrated score.

        Args:
            name: Affiliation or employer name as observed.
            kind: Which calibration table to consult.

        Returns:
            The seeded score, or the unknown floor (prestige/outcome None).
        """
        found = self._lookup(name, kind)
        if found is not None:
            return found
        self._log.info("unknown institution", name=name, kind=kind)
        floor = UNKNOWN_UNIVERSITY_SCORE if kind == "university" else UNKNOWN_COMPANY_SCORE
        key = org_key(name) or name
        return InstitutionScore(
            institution_id=ids.institution_id(key),
            kind=kind,
            canonical_name=name,
            score=floor,
            prestige=None,
            outcome=None,
        )
