# Copyright (c) 2026 Venture Hunt. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Funded-team signals collected into bronze; classification happens downstream.

Bronze only records which signals fired (payload["funded_signals"]); the
funded/not-funded verdict and any exclusion is silver/gold logic.
"""

import re
from typing import Final
from urllib.parse import urlparse

from contracts.models import Json
from scrapers.common.jsonutil import get_list, get_map, get_str

FUNDED_PATTERNS: Final[tuple[tuple[str, re.Pattern[str]], ...]] = (
    ("backed_by", re.compile(r"\bbacked by\b", re.IGNORECASE)),
    ("funded_by", re.compile(r"\bfunded by\b", re.IGNORECASE)),
    ("series_round", re.compile(r"\bseries [a-c]\b", re.IGNORECASE)),
    ("preseed", re.compile(r"\bpre-?seed\b", re.IGNORECASE)),
    ("seed_round", re.compile(r"\bseed round\b", re.IGNORECASE)),
    ("yc_batch", re.compile(r"\bYC [SW]\d{2}\b")),
    ("a16z", re.compile(r"\ba16z\b", re.IGNORECASE)),
    ("sequoia", re.compile(r"\bsequoia\b", re.IGNORECASE)),
    ("accel", re.compile(r"\baccel\b", re.IGNORECASE)),
    ("index_ventures", re.compile(r"\bindex ventures\b", re.IGNORECASE)),
    ("lightspeed", re.compile(r"\blightspeed\b", re.IGNORECASE)),
)


def readme_signals(readme_md: str) -> list[str]:
    """Signals fired by the README regex battery.

    Args:
        readme_md: The README markdown.

    Returns:
        Fired signal names, in battery order.
    """
    return [name for name, pattern in FUNDED_PATTERNS if pattern.search(readme_md)]


def _domain(url: str | None) -> str | None:
    if not url:
        return None
    candidate = url if "//" in url else f"https://{url}"
    netloc = urlparse(candidate).netloc.lower().removeprefix("www.")
    return netloc or None


def org_signals(gql_repo: dict[str, Json]) -> list[str]:
    """Signals from the hydrated repo's org and funding fields.

    Args:
        gql_repo: The GraphQL repository object.

    Returns:
        Fired signal names.
    """
    fired: list[str] = []
    owner = get_map(gql_repo, "owner")
    if owner.get("isVerified") is True:
        fired.append("org_verified")
    if get_list(gql_repo, "fundingLinks"):
        fired.append("funding_links")
    org_domain = _domain(get_str(owner, "websiteUrl"))
    homepage_domain = _domain(get_str(gql_repo, "homepageUrl"))
    if org_domain is not None and org_domain == homepage_domain:
        fired.append("org_domain_matches_homepage")
    return fired


def funded_signals(gql_repo: dict[str, Json], readme_md: str | None) -> list[str]:
    """All funded signals for one repo, deduplicated, battery order first.

    Args:
        gql_repo: The GraphQL repository object.
        readme_md: The README markdown, when present.

    Returns:
        Fired signal names.
    """
    fired = readme_signals(readme_md) if readme_md is not None else []
    fired.extend(org_signals(gql_repo))
    return list(dict.fromkeys(fired))
