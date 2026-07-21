"""The unmerge path: retract a wrong link, repoint the PSR, plan the repairs.

Plan-as-data: the outcome carries the retracted and corrective link rows plus
the follow-up work (re-survivorship of both persons, denorm backfill,
connection rebuild, venture-score invalidation SQL). No fact row is ever
touched - the payoff of keying facts on source records. SQL statements here
interpolate only identifier-guarded names and escaped UUID literals, which is
what makes the per-file S608 ignore safe.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from contracts.models import Json, SinkRow
from er.cluster import link_row
from scrapers.common.jsonutil import as_sink, get_str
from scrapers.common.state import require_identifier

CORRECTIVE_METHOD: Final[str] = "human_review"
CORRECTIVE_CONFIDENCE: Final[float] = 0.95


class UnknownLinkError(LookupError):
    """Raised when the link to retract is absent or not active."""

    def __init__(self, link_id: str) -> None:
        """Name the missing link."""
        super().__init__(f"no active link {link_id} to unmerge")


@dataclass(frozen=True, slots=True)
class UnmergeRequest:
    """An analyst's decision to move one PSR to another person."""

    link_id: str
    to_person_id: str
    reason: str
    reviewer_note: str
    actor: str


@dataclass(frozen=True, slots=True)
class UnmergeOutcome:
    """Everything the unmerge implies, as data."""

    retracted_link: SinkRow
    corrective_link: SinkRow
    source_record_id: str
    affected_person_ids: tuple[str, str]
    invalidation_statements: tuple[str, ...]


def plan_unmerge(
    request: UnmergeRequest,
    links: Sequence[dict[str, Json]],
    *,
    clock: Callable[[], datetime],
    pipeline_version: str,
    catalog: str,
) -> UnmergeOutcome:
    """Plan one unmerge: retraction, corrective link, and follow-up work.

    Args:
        request: The analyst decision.
        links: Current silver.person_source_link rows.
        clock: Injected time source.
        pipeline_version: Stamped on the corrective link.
        catalog: Target catalog for the invalidation SQL (identifier-guarded).

    Returns:
        The planned outcome. A missing or already-retracted link surfaces
        as UnknownLinkError.
    """
    original = _active_link(links, request.link_id)
    psr = get_str(original, "source_record_id") or ""
    from_person = get_str(original, "person_id") or ""
    now = clock()
    retracted: SinkRow = {key: as_sink(value) for key, value in original.items()}
    retracted["status"] = "retracted"
    retracted["retracted_at"] = now
    retracted["retracted_by"] = request.actor
    retracted["retracted_reason"] = request.reason
    corrective = link_row(
        request.to_person_id,
        psr,
        method=CORRECTIVE_METHOD,
        confidence=CORRECTIVE_CONFIDENCE,
        evidence={"rule": "unmerge correction", "reviewer_note": request.reviewer_note},
        matched_at=now,
        pipeline_version=pipeline_version,
    )
    affected = (from_person, request.to_person_id)
    return UnmergeOutcome(
        retracted_link=retracted,
        corrective_link=corrective,
        source_record_id=psr,
        affected_person_ids=affected,
        invalidation_statements=tuple(_invalidation_sql(catalog, person) for person in affected),
    )


def _active_link(links: Sequence[dict[str, Json]], link_id: str) -> dict[str, Json]:
    for row in links:
        if row.get("link_id") == link_id and row.get("status") == "active":
            return row
    raise UnknownLinkError(link_id)


def _escape(value: str) -> str:
    return value.replace("'", "''")


def _invalidation_sql(catalog: str, person_id: str) -> str:
    """Mark every affected venture score stale so rescoring triggers."""
    safe_catalog = require_identifier(catalog)
    person = _escape(person_id)
    return (
        f"UPDATE {safe_catalog}.gold.venture_score SET is_latest = false "
        f"WHERE venture_id IN (SELECT venture_id FROM {safe_catalog}.gold.venture_member "
        f"WHERE person_id = '{person}')"
    )
