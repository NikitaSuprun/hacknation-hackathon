# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Person-id allocation: random for live runs, seeded for fixture reproduction.

Golden person ids are UUIDv4 minted once and never derived from cluster
content, so re-clustering can never silently rename a person. The seeded
allocator lets offline runs land clusters on the committed fixture ids.
"""

from collections.abc import Iterable, Mapping
from typing import Final, Protocol

from contracts.models import Json
from tools import ids


class PersonIdAllocator(Protocol):
    """Chooses the golden person id for one cluster of PSR ids."""

    def allocate(self, cluster: frozenset[str]) -> str:
        """Return the person id for a cluster of source_record_ids."""
        ...


class RandomPersonIdAllocator:
    """Mints a fresh UUIDv4 per cluster (the live path)."""

    def allocate(self, cluster: frozenset[str]) -> str:
        """Mint a new person id.

        Args:
            cluster: The cluster's source_record_ids (unused; ids are random).

        Returns:
            A fresh UUIDv4 string.
        """
        del cluster
        return ids.new_random_id()


class SeededPersonIdAllocator:
    """Maps clusters onto known person ids; any member hit wins."""

    def __init__(self, mapping: Mapping[str, str], fallback: PersonIdAllocator) -> None:
        """Bind the psr-to-person seed map and the fallback allocator."""
        self._mapping: Final[Mapping[str, str]] = mapping
        self._fallback: Final[PersonIdAllocator] = fallback

    def allocate(self, cluster: frozenset[str]) -> str:
        """Return the seeded person id of the first known member.

        Args:
            cluster: The cluster's source_record_ids.

        Returns:
            The seeded person id, or a fallback allocation when no member
            is known.
        """
        for member in sorted(cluster):
            known = self._mapping.get(member)
            if known is not None:
                return known
        return self._fallback.allocate(cluster)


def allocator_from_links(
    link_rows: Iterable[Mapping[str, Json]], *, fallback: PersonIdAllocator
) -> SeededPersonIdAllocator:
    """Seed an allocator from existing active person_source_link rows.

    Args:
        link_rows: silver.person_source_link rows.
        fallback: Allocator used for clusters with no seeded member.

    Returns:
        The seeded allocator.
    """
    mapping: dict[str, str] = {}
    for row in link_rows:
        person = row.get("person_id")
        psr = row.get("source_record_id")
        if row.get("status") == "active" and isinstance(person, str) and isinstance(psr, str):
            mapping[psr] = person
    return SeededPersonIdAllocator(mapping, fallback)
