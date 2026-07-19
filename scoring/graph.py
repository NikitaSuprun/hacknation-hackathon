# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""The person-to-person collaboration graph (centrality + funded-founder paths).

silver.person_connection carries one row per edge type; parallel edges
collapse into one weighted edge (weights summed). networkx builds the graph,
but it ships no py.typed marker, so the untyped surface is confined to the
constructor seam and everything downstream works on a typed adjacency.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import cast

import networkx as nx  # pyright: ignore[reportMissingTypeStubs] - networkx ships no py.typed marker

from scoring.snapshot import Row, get_float
from scrapers.common.jsonutil import get_str


@dataclass(frozen=True, slots=True)
class CollabGraph:
    """Typed view of the collaboration graph: node -> neighbor -> weight."""

    adjacency: Mapping[str, Mapping[str, float]]

    def neighbors(self, person_id: str) -> frozenset[str]:
        """Direct collaborators of one person.

        Args:
            person_id: The person node.

        Returns:
            The neighbor set (empty for unknown nodes).
        """
        return frozenset(self.adjacency.get(person_id, {}))

    def two_hop(self, person_id: str) -> frozenset[str]:
        """Collaborators-of-collaborators, excluding self and direct neighbors.

        Args:
            person_id: The person node.

        Returns:
            The second-ring set.
        """
        direct = self.neighbors(person_id)
        ring = {second for first in direct for second in self.adjacency.get(first, {})}
        return frozenset(ring - direct - {person_id})


def build_graph(connections: tuple[Row, ...]) -> CollabGraph:
    """Build the collaboration graph from silver.person_connection rows.

    Args:
        connections: The connection rows (one per edge type).

    Returns:
        The typed graph; parallel edge types collapse with summed weights.
    """
    graph = nx.Graph()  # pyright: ignore[reportUnknownVariableType] - untyped networkx constructor
    for row in connections:
        mapping = dict(row)
        person_a = get_str(mapping, "person_a_id")
        person_b = get_str(mapping, "person_b_id")
        if person_a is None or person_b is None or person_a == person_b:
            continue
        weight = get_float(row, "weight") or 1.0
        if graph.has_edge(person_a, person_b):  # pyright: ignore[reportUnknownMemberType] - untyped networkx
            weight += _edge_weight(graph, person_a, person_b)  # pyright: ignore[reportUnknownArgumentType] - untyped networkx
        graph.add_edge(person_a, person_b, weight=weight)  # pyright: ignore[reportUnknownMemberType] - untyped networkx
    adjacency: dict[str, dict[str, float]] = {}
    for node in graph.nodes:  # pyright: ignore[reportUnknownMemberType,reportUnknownVariableType] - untyped networkx
        node_id = str(node)  # pyright: ignore[reportUnknownArgumentType] - nodes are the str person ids
        adjacency[node_id] = {
            str(other): _edge_weight(graph, node_id, str(other))  # pyright: ignore[reportUnknownArgumentType] - nodes are the str person ids
            for other in graph.neighbors(node_id)  # pyright: ignore[reportUnknownMemberType,reportUnknownVariableType] - untyped networkx
        }
    return CollabGraph(adjacency=adjacency)


def _edge_weight(graph: object, person_a: str, person_b: str) -> float:
    edges = getattr(graph, "edges", None)
    if edges is None:
        return 0.0
    data = edges[person_a, person_b]
    if not isinstance(data, dict):
        return 0.0
    weight = cast("dict[str, object]", data).get("weight", 0.0)
    return float(weight) if isinstance(weight, int | float) else 0.0


def centrality(graph: CollabGraph, person_id: str) -> float:
    """Degree + 2-hop reach, normalized by the reachable maximum.

    Args:
        graph: The collaboration graph.
        person_id: The person to measure.

    Returns:
        0..1 share of the other nodes within two hops.
    """
    nodes = set(graph.adjacency)
    others = len(nodes | {person_id}) - 1
    if others <= 0:
        return 0.0
    reach = len(graph.neighbors(person_id)) + len(graph.two_hop(person_id))
    return round(reach / others, 4)


def funded_founder_hops(
    graph: CollabGraph,
    person_id: str,
    is_funded_founder: Callable[[str], bool],
    max_hops: int = 2,
) -> int | None:
    """Shortest hop count from a person to any funded founder.

    Args:
        graph: The collaboration graph.
        person_id: The starting person.
        is_funded_founder: Predicate over person ids.
        max_hops: Search radius (default two hops).

    Returns:
        The hop count (0 when the person is a funded founder), or None
        when no funded founder is reachable within the radius.
    """
    if is_funded_founder(person_id):
        return 0
    frontier = {person_id}
    seen = {person_id}
    for hop in range(1, max_hops + 1):
        frontier = {
            neighbor
            for node in frontier
            for neighbor in graph.neighbors(node)
            if neighbor not in seen
        }
        if any(is_funded_founder(neighbor) for neighbor in frontier):
            return hop
        seen |= frontier
    return None
