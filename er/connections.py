"""Stage 5: the collaboration graph (silver.person_connection).

Edges come from shared-artifact self-joins over active links; person_a_id <
person_b_id is enforced structurally. Edge weight sums a recency decay per
shared artifact: 1.0 within a year of the artifact's last activity, halved
per year beyond that.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Final

from contracts.models import Json, SinkRow, SinkValue
from scrapers.common.jsonutil import get_str

FRESH_DAYS: Final[int] = 365
_DAYS_PER_YEAR: Final[float] = 365.0
_HALVING: Final[float] = 0.5


@dataclass(frozen=True, slots=True)
class SharedArtifact:
    """One artifact shared by two persons, with its activity window."""

    artifact_id: str
    first_seen: date
    last_seen: date


def decay(age_days: int) -> float:
    """Recency decay of one shared artifact.

    Args:
        age_days: Days since the artifact's last shared activity.

    Returns:
        1.0 within FRESH_DAYS, else 0.5 per elapsed year.
    """
    if age_days <= FRESH_DAYS:
        return 1.0
    return _HALVING ** (age_days / _DAYS_PER_YEAR)


def _date_of(value: Json) -> date | None:
    if not isinstance(value, str) or not value:
        return None
    return datetime.fromisoformat(value).date() if "T" in value else date.fromisoformat(value)


@dataclass(frozen=True, slots=True)
class _Membership:
    """One person's dated participation in one artifact."""

    artifact_id: str
    person_id: str
    start: date | None
    end: date | None


def _memberships(  # noqa: PLR0913 - fact tables differ in exactly these column names
    rows: Sequence[dict[str, Json]],
    links: Mapping[str, str],
    artifact_col: str,
    start_col: str | None,
    end_col: str | None,
    fallback_dates: Mapping[str, date | None],
) -> list[_Membership]:
    members: list[_Membership] = []
    for row in rows:
        artifact = get_str(row, artifact_col)
        psr = get_str(row, "source_record_id")
        if artifact is None or psr is None or psr not in links:
            continue
        start = _date_of(row.get(start_col)) if start_col is not None else None
        end = _date_of(row.get(end_col)) if end_col is not None else None
        anchor = fallback_dates.get(artifact)
        members.append(
            _Membership(
                artifact_id=artifact,
                person_id=links[psr],
                start=start if start is not None else anchor,
                end=end if end is not None else anchor,
            )
        )
    return members


def _pair_edges(members: Sequence[_Membership]) -> dict[tuple[str, str], list[SharedArtifact]]:
    by_artifact: dict[str, list[_Membership]] = {}
    for member in members:
        by_artifact.setdefault(member.artifact_id, []).append(member)
    edges: dict[tuple[str, str], list[SharedArtifact]] = {}
    for artifact_id, group in sorted(by_artifact.items()):
        for pair, shared in _artifact_pairs(artifact_id, group):
            edges.setdefault(pair, []).append(shared)
    return edges


def _artifact_pairs(
    artifact_id: str, group: Sequence[_Membership]
) -> list[tuple[tuple[str, str], SharedArtifact]]:
    """All distinct-person pairs sharing one artifact, with their windows."""
    ordered = sorted(group, key=lambda member: member.person_id)
    pairs: list[tuple[tuple[str, str], SharedArtifact]] = []
    for index, a in enumerate(ordered):
        for b in ordered[index + 1 :]:
            if a.person_id == b.person_id:
                continue
            window = _shared_window(a, b)
            if window is None:
                continue
            start, end = window
            pairs.append(
                (
                    (a.person_id, b.person_id),
                    SharedArtifact(artifact_id=artifact_id, first_seen=start, last_seen=end),
                )
            )
    return pairs


def _shared_window(a: _Membership, b: _Membership) -> tuple[date, date] | None:
    starts = [d for d in (a.start, b.start) if d is not None]
    ends = [d for d in (a.end, b.end) if d is not None]
    if not starts or not ends:
        return None
    return max(starts), max(ends)


def _edge_rows(
    edges: Mapping[tuple[str, str], list[SharedArtifact]],
    connection_type: str,
    now: datetime,
) -> list[SinkRow]:
    rows: list[SinkRow] = []
    today = now.date()
    for (person_a, person_b), shared in sorted(edges.items()):
        weight = sum(decay((today - artifact.last_seen).days) for artifact in shared)
        evidence = list[SinkValue](sorted(artifact.artifact_id for artifact in shared))
        rows.append(
            {
                "person_a_id": person_a,
                "person_b_id": person_b,
                "connection_type": connection_type,
                "weight": round(weight, 4),
                "evidence": evidence,
                "first_seen": min(artifact.first_seen for artifact in shared),
                "last_seen": max(artifact.last_seen for artifact in shared),
                "updated_at": now,
            }
        )
    return rows


def build_connections(  # noqa: PLR0913 - the three edge types plus their date anchors
    authorships: Sequence[dict[str, Json]],
    contributions: Sequence[dict[str, Json]],
    officers: Sequence[dict[str, Json]],
    publications: Sequence[dict[str, Json]],
    active_links: Mapping[str, str],
    *,
    clock: Callable[[], datetime],
) -> list[SinkRow]:
    """Build every coauthor / co_contributor / co_officer edge.

    Args:
        authorships: silver.authorship rows.
        contributions: silver.contribution rows.
        officers: silver.officer rows.
        publications: silver.publication rows (publication dates).
        active_links: source_record_id to person_id for active links.
        clock: Injected time source.

    Returns:
        silver.person_connection rows with person_a_id < person_b_id.
    """
    now = clock()
    published: dict[str, date | None] = {
        pub_id: _date_of(row.get("published_at"))
        for row in publications
        if (pub_id := get_str(row, "publication_id")) is not None
    }
    coauthors = _memberships(authorships, active_links, "publication_id", None, None, published)
    contributors = _memberships(
        contributions, active_links, "project_id", "first_commit_at", "last_commit_at", {}
    )
    officerships = _memberships(
        officers, active_links, "company_id", "registered_at", "deregistered_at", {}
    )
    for index, member in enumerate(officerships):
        if member.end is None:
            officerships[index] = _Membership(
                artifact_id=member.artifact_id,
                person_id=member.person_id,
                start=member.start,
                end=member.start,
            )
    return [
        *_edge_rows(_pair_edges(coauthors), "coauthor", now),
        *_edge_rows(_pair_edges(contributors), "co_contributor", now),
        *_edge_rows(_pair_edges(officerships), "co_officer", now),
    ]
