# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Deterministic stand-in embeddings until `databricks-gte-large-en` is wired up.

Each token maps to a seeded pseudo-random unit vector and a text is the
L2-normalized sum of its token vectors, so texts sharing vocabulary correlate:
"robotic grasping" scores near "robotics manipulation ideal" and far from
"database systems". That property carries the WS-D acceptance check that the
robotics founder tops domain-fit against the robotics ideal profile.
"""

import hashlib
import math
import random
import re
from functools import cache
from typing import Final

EMBEDDING_DIM: Final[int] = 1024

_TOKEN_PATTERN: Final[re.Pattern[str]] = re.compile(r"[a-z0-9]+")


@cache
def _token_vector(token: str) -> tuple[float, ...]:
    seed = int.from_bytes(hashlib.sha256(token.encode("utf-8")).digest()[:8], "big")
    rng = random.Random(seed)  # noqa: S311 - deterministic fixture vectors, not cryptography
    return tuple(rng.gauss(0.0, 1.0) for _ in range(EMBEDDING_DIM))


def fake_embedding(text: str) -> list[float]:
    """Embed a text as the unit-normalized sum of its token vectors.

    Args:
        text: Free text; tokenized on lowercase alphanumeric runs.

    Returns:
        A 1024-dim L2-normalized vector; deterministic for identical input.
    """
    tokens = _TOKEN_PATTERN.findall(text.lower()) or ["<empty>"]
    summed = [0.0] * EMBEDDING_DIM
    for token in tokens:
        vector = _token_vector(token)
        for i in range(EMBEDDING_DIM):
            summed[i] += vector[i]
    norm = math.sqrt(sum(component * component for component in summed))
    return [component / norm for component in summed]


def cosine(left: list[float], right: list[float]) -> float:
    """Dot product of two unit vectors (their cosine similarity).

    Args:
        left: A unit vector.
        right: A unit vector of the same dimension.

    Returns:
        The cosine similarity.
    """
    return sum(a * b for a, b in zip(left, right, strict=True))
