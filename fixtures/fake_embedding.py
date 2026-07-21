"""Deterministic stand-in embeddings until `databricks-gte-large-en` is wired up.

Each token maps to a hash-derived vector and a text is the L2-normalized sum
of its token vectors, so texts sharing vocabulary correlate: "robotic
grasping" scores near "robotics manipulation ideal" and far from "database
systems". That property carries the WS-D acceptance check that the robotics
founder tops domain-fit against the robotics ideal profile.

Components are sha256 integers mapped to [-1, 1) by exact division; the only
floating-point operations are add/multiply/divide/sqrt, all IEEE-754
correctly rounded - so the committed fixture bytes are identical on every
platform (libm functions like log/cos are not, which broke CI on Linux).
"""

import hashlib
import math
import re
from functools import cache
from typing import Final

EMBEDDING_DIM: Final[int] = 1024

_COMPONENT_BYTES: Final[int] = 8
_COMPONENTS_PER_DIGEST: Final[int] = 32 // _COMPONENT_BYTES
_TOKEN_PATTERN: Final[re.Pattern[str]] = re.compile(r"[a-z0-9]+")


@cache
def _token_vector(token: str) -> tuple[float, ...]:
    components: list[float] = []
    for block in range(EMBEDDING_DIM // _COMPONENTS_PER_DIGEST):
        digest = hashlib.sha256(f"{token}:{block}".encode()).digest()
        for i in range(_COMPONENTS_PER_DIGEST):
            k = int.from_bytes(digest[i * _COMPONENT_BYTES : (i + 1) * _COMPONENT_BYTES], "big")
            components.append(k / 2**63 - 1.0)
    return tuple(components)


def fake_embedding(text: str) -> list[float]:
    """Embed a text as the unit-normalized sum of its token vectors.

    Args:
        text: Free text; tokenized on lowercase alphanumeric runs.

    Returns:
        A 1024-dim L2-normalized vector; bit-identical for identical input
        on any platform.
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
