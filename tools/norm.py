# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Normalizers feeding entity resolution: same input, same output, everywhere.

Rules per docs/plan/reference/entity-resolution.md: GitHub noreply addresses
attribute commits but are banned from cross-source email matching; generic
inboxes never identify a person; university aliases fold to one canonical name.
"""

import re
import unicodedata
from typing import Final

_TITLES: Final[frozenset[str]] = frozenset(
    {"dr", "prof", "professor", "phd", "md", "msc", "bsc", "ing", "mr", "mrs", "ms"}
)

_GENERIC_INBOXES: Final[frozenset[str]] = frozenset(
    {
        "admin",
        "contact",
        "hello",
        "info",
        "mail",
        "no-reply",
        "noreply",
        "office",
        "sales",
        "support",
        "team",
        "webmaster",
    }
)

_NOREPLY_DOMAIN: Final[str] = "users.noreply.github.com"

_LEGAL_SUFFIXES: Final[frozenset[str]] = frozenset(
    {"ag", "gmbh", "sa", "sarl", "inc", "llc", "ltd", "se", "kg", "co", "corp", "plc"}
)

# Alias table: every observed spelling folds to one canonical org key.
_ORG_ALIASES: Final[dict[str, str]] = {
    "ethz": "eth zurich",
    "eth zurich": "eth zurich",
    "eidgenossische technische hochschule zurich": "eth zurich",
    "swiss federal institute of technology": "eth zurich",
    "swiss federal institute of technology zurich": "eth zurich",
    "swiss federal institute of technology in zurich": "eth zurich",
    "epfl": "epfl",
    "ecole polytechnique federale de lausanne": "epfl",
    "swiss federal institute of technology lausanne": "epfl",
    "uzh": "university of zurich",
    "university of zurich": "university of zurich",
    "universitat zurich": "university of zurich",
    "mit": "mit",
    "massachusetts institute of technology": "mit",
    "kth": "kth",
    "kth royal institute of technology": "kth",
}

_WHITESPACE: Final[re.Pattern[str]] = re.compile(r"\s+")
_NAME_PUNCTUATION: Final[re.Pattern[str]] = re.compile(r"[.,;:!?'\"()\[\]]")


def _strip_diacritics(text: str) -> str:
    replaced = text.replace("ß", "ss")
    decomposed = unicodedata.normalize("NFKD", replaced)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def name_norm(full_name: str) -> str:
    """Lowercase, de-accent, and strip titles/punctuation from a person name.

    Args:
        full_name: Name as observed at the source.

    Returns:
        The normalized name; empty string when nothing survives.
    """
    lowered = _strip_diacritics(full_name).lower()
    cleaned = _NAME_PUNCTUATION.sub(" ", lowered)
    tokens = [t for t in _WHITESPACE.split(cleaned) if t and t not in _TITLES]
    return " ".join(tokens)


def email_norm(email: str) -> str | None:
    """Normalize an email for cross-source identity matching.

    Args:
        email: Raw address.

    Returns:
        The lowered address, or None when it must not identify a person
        (GitHub noreply, generic inboxes, malformed).
    """
    lowered = email.strip().lower()
    if lowered.count("@") != 1:
        return None
    local, domain = lowered.split("@")
    if not local or not domain:
        return None
    if domain == _NOREPLY_DOMAIN:
        return None
    if local in _GENERIC_INBOXES:
        return None
    return lowered


def email_domain(email: str) -> str | None:
    """Blocking key: the domain of a normalized email.

    Args:
        email: Raw address.

    Returns:
        The domain, or None when the address is excluded from matching.
    """
    normalized = email_norm(email)
    if normalized is None:
        return None
    return normalized.split("@")[1]


def org_norm(org: str) -> str:
    """Normalize an organisation string: de-accent, strip legal suffixes, fold aliases.

    Args:
        org: Affiliation or company name as observed.

    Returns:
        The canonical org key; empty string when nothing survives.
    """
    lowered = _strip_diacritics(org).lower()
    cleaned = _NAME_PUNCTUATION.sub(" ", lowered)
    tokens = [t for t in _WHITESPACE.split(cleaned) if t]
    while tokens and tokens[-1] in _LEGAL_SUFFIXES:
        tokens.pop()
    joined = " ".join(tokens)
    return _ORG_ALIASES.get(joined, joined)


def url_norm(url: str) -> str | None:
    """Normalize a URL for equality matching (rule D3).

    Args:
        url: Raw URL or bare domain.

    Returns:
        Scheme-less, www-less, lowered-host URL without trailing slash,
        query, or fragment; None for empty input.
    """
    stripped = url.strip()
    if not stripped:
        return None
    without_scheme = re.sub(r"^https?://", "", stripped, flags=re.IGNORECASE)
    without_fragment = without_scheme.split("#")[0].split("?")[0]
    host, _, path = without_fragment.partition("/")
    host = host.lower().removeprefix("www.")
    if not host:
        return None
    result = host if not path else f"{host}/{path}"
    return result.rstrip("/")
