# Copyright (c) 2026 Venture Hunt. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Stage 6 library: person profile texts and unit-norm profile embeddings.

WS-E owns full gold.person_features rows; this module renders deterministic
profile texts, embeds them through the LLM seam (asserting the 1024-dim
unit-norm contract), and shapes the partial feature rows the demo writer
upserts.
"""

import math
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from typing import Final

from contracts.interfaces import LLMClient
from contracts.models import Json, SinkRow, SinkValue
from er.models import PsrView, psr_view

EMBEDDING_DIM: Final[int] = 1024
_UNIT_TOLERANCE: Final[float] = 1e-6


class ProfileEmbeddingError(ValueError):
    """The embedding backend violated the 1024-dim unit-norm contract."""


class ProfileDimensionError(ProfileEmbeddingError):
    """The embedding came back with the wrong dimensionality."""

    def __init__(self, actual: int) -> None:
        """Report actual versus expected dims."""
        super().__init__(f"embedding has {actual} dims, expected {EMBEDDING_DIM}")


class ProfileNormError(ProfileEmbeddingError):
    """The embedding is not L2-normalized."""

    def __init__(self, magnitude: float) -> None:
        """Report the offending magnitude."""
        super().__init__(f"embedding magnitude is {magnitude:.8f}, expected 1.0")


def render_profile_text(views: Sequence[PsrView]) -> str:
    """Deterministic profile text from a person's linked source records.

    Args:
        views: The person's linked PSR views.

    Returns:
        A stable space-joined keyword/bio/affiliation text.
    """
    parts: list[str] = []
    seen: set[str] = set()
    ordered = sorted(views, key=lambda view: view.source_record_id)
    for view in ordered:
        for token in (*view.keywords, view.affiliation_raw or "", view.bio or ""):
            cleaned = token.strip().lower()
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                parts.append(cleaned)
    return " ".join(parts)


def embed_profile(text: str, llm: LLMClient) -> list[float]:
    """Embed one profile text, enforcing the vector contract.

    Args:
        text: The profile text.
        llm: The embedding client.

    Returns:
        The 1024-dim L2-normalized vector.

    Raises:
        ProfileDimensionError: On a wrong dimensionality.
        ProfileNormError: On a non-unit norm.
    """
    vector = llm.embed(text)
    if len(vector) != EMBEDDING_DIM:
        raise ProfileDimensionError(len(vector))
    magnitude = math.sqrt(sum(component * component for component in vector))
    if abs(magnitude - 1.0) > _UNIT_TOLERANCE:
        raise ProfileNormError(magnitude)
    return vector


def embedding_rows(
    profile_texts: Mapping[str, str],
    llm: LLMClient,
    *,
    embedding_model: str,
    clock: Callable[[], datetime],
) -> list[SinkRow]:
    """Partial gold.person_features rows carrying the embedding columns.

    Args:
        profile_texts: Profile text per person_id.
        llm: The embedding client.
        embedding_model: Model name stamped on each row.
        clock: Injected time source.

    Returns:
        Rows with person_id, profile_text, profile_embedding,
        embedding_model, and computed_at (WS-E owns the rest).
    """
    now = clock()
    rows: list[SinkRow] = []
    for person_id in sorted(profile_texts):
        text = profile_texts[person_id]
        vector = list[SinkValue](embed_profile(text, llm))
        rows.append(
            {
                "person_id": person_id,
                "profile_text": text,
                "profile_embedding": vector,
                "embedding_model": embedding_model,
                "computed_at": now,
            }
        )
    return rows


def profile_texts_by_person(
    psr_rows: Sequence[dict[str, Json]], active_links: Mapping[str, str]
) -> dict[str, str]:
    """Render one profile text per linked person.

    Args:
        psr_rows: The full PSR universe.
        active_links: source_record_id to person_id for active links.

    Returns:
        Profile texts keyed by person_id.
    """
    views_by_person: dict[str, list[PsrView]] = {}
    for row in psr_rows:
        view = psr_view(row)
        person = active_links.get(view.source_record_id)
        if person is not None:
            views_by_person.setdefault(person, []).append(view)
    return {person: render_profile_text(views) for person, views in sorted(views_by_person.items())}
