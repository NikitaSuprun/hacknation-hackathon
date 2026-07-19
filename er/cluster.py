# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Clustering auto-matches into persons and building reversible links.

networkx is the one untyped vendor surface here; every touchpoint is confined
to `_components` behind typed signatures. The same-source-collision guard
enforces the precision guardrail: a second PSR of one source type never merges
into a cluster automatically - it routes to review instead.
"""

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

import networkx  # pyright: ignore[reportMissingTypeStubs] - vendor ships no stubs

from contracts.models import Json, SinkRow
from er.allocator import PersonIdAllocator
from er.models import METHOD_PRIORITY, ReviewItem, RuleMatch
from scrapers.common.jsonutil import as_sink
from tools import ids


@dataclass(frozen=True, slots=True)
class ClusterResult:
    """Guarded clusters plus the members ejected by the same-source guard."""

    clusters: tuple[frozenset[str], ...]
    ejected: tuple[tuple[str, frozenset[str]], ...]


def components(matches: Iterable[RuleMatch]) -> list[frozenset[str]]:
    """Connected components over the auto matches.

    Args:
        matches: Pairwise match decisions; only auto=True edges cluster.

    Returns:
        The clusters, sorted by their smallest member for determinism.
    """
    graph = networkx.Graph()  # pyright: ignore[reportUnknownVariableType] - vendor API is untyped
    for match in matches:
        if match.auto:
            graph.add_edge(match.left, match.right)  # pyright: ignore[reportUnknownMemberType] - vendor API is untyped
    raw: Iterable[set[str]] = networkx.connected_components(graph)  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType] - vendor API is untyped
    return sorted((frozenset(component) for component in raw), key=min)


def guard_same_source(
    clusters: Sequence[frozenset[str]], sources: Mapping[str, str]
) -> ClusterResult:
    """Eject same-source collisions from every cluster.

    When a cluster holds two PSRs of one source type, only the first (sorted)
    stays; the rest are ejected toward human review.

    Args:
        clusters: The raw connected components.
        sources: source_record_id to source type.

    Returns:
        The guarded clusters and (ejected_psr, remaining_cluster) pairs.
    """
    guarded: list[frozenset[str]] = []
    ejected: list[tuple[str, frozenset[str]]] = []
    for cluster in clusters:
        kept: dict[str, str] = {}
        dropped: list[str] = []
        for member in sorted(cluster):
            source = sources.get(member, "")
            if source in kept.values():
                dropped.append(member)
            else:
                kept[member] = source
        remaining = frozenset(kept)
        guarded.append(remaining)
        ejected.extend((member, remaining) for member in dropped)
    return ClusterResult(clusters=tuple(guarded), ejected=tuple(ejected))


def _best_incident(member: str, matches: Sequence[RuleMatch]) -> RuleMatch | None:
    incident = [match for match in matches if match.auto and member in (match.left, match.right)]
    if not incident:
        return None
    return min(
        incident,
        key=lambda match: (METHOD_PRIORITY.index(match.method), match.left, match.right),
    )


def build_links(  # noqa: PLR0913 - clustering needs the full linking context
    clusters: Iterable[frozenset[str]],
    matches: Sequence[RuleMatch],
    allocator: PersonIdAllocator,
    *,
    linked: Mapping[str, str],
    clock: Callable[[], datetime],
    pipeline_version: str,
) -> list[SinkRow]:
    """One active link per newly matched PSR; already-linked PSRs are skipped.

    Each link's method and evidence come from the highest-priority auto rule
    incident to that PSR (D1 > D2 > D3 > D4 > D5 > splink > llm).

    Args:
        clusters: Guarded clusters of source_record_ids.
        matches: All auto matches (the evidence source).
        allocator: Person-id chooser for clusters with no linked member.
        linked: Existing active links (source_record_id to person_id).
        clock: Injected time source.
        pipeline_version: Stamped on every link.

    Returns:
        The new silver.person_source_link rows.
    """
    now = clock()
    rows: list[SinkRow] = []
    for cluster in clusters:
        person = _cluster_person(cluster, linked, allocator)
        for member in sorted(cluster):
            if member in linked:
                continue
            best = _best_incident(member, matches)
            if best is None:
                continue
            rows.append(
                link_row(
                    person,
                    member,
                    method=best.method,
                    confidence=best.confidence,
                    evidence=best.evidence,
                    matched_at=now,
                    pipeline_version=pipeline_version,
                )
            )
    return rows


def _cluster_person(
    cluster: frozenset[str], linked: Mapping[str, str], allocator: PersonIdAllocator
) -> str:
    for member in sorted(cluster):
        person = linked.get(member)
        if person is not None:
            return person
    return allocator.allocate(cluster)


def link_row(  # noqa: PLR0913 - the link row has exactly these seven degrees of freedom
    person_id: str,
    source_record_id: str,
    *,
    method: str,
    confidence: float,
    evidence: Mapping[str, Json],
    matched_at: datetime,
    pipeline_version: str,
) -> SinkRow:
    """Render one active person_source_link row in DDL shape.

    Args:
        person_id: The golden person.
        source_record_id: The linked PSR.
        method: The match method (drives the deterministic link_id).
        confidence: Match confidence in [0, 1].
        evidence: Rule evidence, stored as VARIANT.
        matched_at: Link timestamp.
        pipeline_version: Producing pipeline version.

    Returns:
        The link row.
    """
    return {
        "link_id": ids.link_id(person_id, source_record_id, method),
        "person_id": person_id,
        "source_record_id": source_record_id,
        "match_confidence": confidence,
        "match_method": method,
        "evidence": as_sink(dict(evidence)),
        "pipeline_version": pipeline_version,
        "matched_at": matched_at,
        "status": "active",
        "retracted_at": None,
        "retracted_by": None,
        "retracted_reason": None,
    }


def review_item_from_ejection(
    ejection: tuple[str, frozenset[str]], person_by_psr: Mapping[str, str]
) -> ReviewItem | None:
    """Turn one same-source ejection into a review candidate.

    Args:
        ejection: The (ejected_psr, remaining_cluster) pair.
        person_by_psr: Person assignment of the remaining members.

    Returns:
        The review item, or None when the cluster's person is unknown.
    """
    member, cluster = ejection
    for other in sorted(cluster):
        person = person_by_psr.get(other)
        if person is not None:
            return ReviewItem(
                source_record_id=member,
                candidate_person_id=person,
                score=0.5,
                method="same_source_collision",
                features={"rule": "same-source collision", "cluster": list[Json](sorted(cluster))},
            )
    return None
