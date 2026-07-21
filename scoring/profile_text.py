"""Deterministic "what they build/research" texts for the domain-fit embedding.

The embedding does topic-fit only (prestige and magnitude live in the
structured features), so the rendering is a plain, ordered concatenation of
observed topical signals — same input, same text, everywhere.
"""

import re
from collections.abc import Sequence
from typing import Final

from scoring.snapshot import Row
from scrapers.common.jsonutil import get_list, get_str

_TOKEN_SPLIT: Final[re.Pattern[str]] = re.compile(r"[^a-z0-9]+")


def _phrases(values: Sequence[object]) -> list[str]:
    return [value.lower() for value in values if isinstance(value, str)]


def _dedupe(tokens: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for token in tokens:
        if token and token not in seen:
            seen.add(token)
            ordered.append(token)
    return ordered


def _tokens(text: str) -> list[str]:
    return [token for token in _TOKEN_SPLIT.split(text.lower()) if token]


def render_person_text(person: Row, projects: Sequence[Row], publications: Sequence[Row]) -> str:
    """Render one person's topical profile text.

    Args:
        person: The silver.person row.
        projects: Projects the person contributed to.
        publications: Publications the person authored.

    Returns:
        A deduplicated token sequence: headline, project topics/tags,
        publication concepts — deterministic for identical inputs.
    """
    tokens: list[str] = []
    headline = get_str(dict(person), "headline")
    if headline is not None:
        tokens.extend(_tokens(headline))
    for project in projects:
        mapping = dict(project)
        tokens.extend(_phrases(get_list(mapping, "topics")))
        tokens.extend(_phrases(get_list(mapping, "market_tags")))
    for publication in publications:
        tokens.extend(_phrases(get_list(dict(publication), "concepts")))
    return " ".join(_dedupe(tokens))


def render_ideal_text(profile_json: Row) -> str:
    """Render the ideal-candidate profile as its domain-fit text.

    Args:
        profile_json: The gold.ideal_candidate.profile_json payload.

    Returns:
        Narrative plus keywords plus sectors, tokenized and deduplicated.
    """
    mapping = dict(profile_json)
    tokens: list[str] = []
    narrative = get_str(mapping, "narrative")
    if narrative is not None:
        tokens.extend(_tokens(narrative))
    tokens.extend(_phrases(get_list(mapping, "keywords")))
    tokens.extend(_phrases(get_list(mapping, "sectors")))
    return " ".join(_dedupe(tokens))


def domain_fit(left: Sequence[float], right: Sequence[float]) -> float:
    """Cosine of two unit vectors (their dot product).

    Args:
        left: A unit vector.
        right: A unit vector of the same dimension.

    Returns:
        The similarity in [-1, 1].
    """
    return sum(a * b for a, b in zip(left, right, strict=True))
