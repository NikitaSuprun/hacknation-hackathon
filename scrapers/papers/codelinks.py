# Copyright (c) 2026 Venture Hunt. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Code-link extraction from abstracts and comments (github/gitlab/huggingface)."""

import re
from typing import Final

from scrapers.papers.models import CodeHost, CodeLink

_TAIL: Final[str] = r"(?=[\s).,;\]'\"]|$)"

# Repo names match greedily (dotted names like grasp.anything stay whole);
# trailing '.git' and sentence punctuation are stripped afterwards.
HOST_PATTERNS: Final[tuple[tuple[CodeHost, re.Pattern[str]], ...]] = (
    ("github", re.compile(r"github\.com/([\w.-]+)/([\w.-]+)" + _TAIL, re.IGNORECASE)),
    ("gitlab", re.compile(r"gitlab\.com/([\w.-]+)/([\w.-]+)" + _TAIL, re.IGNORECASE)),
    (
        "huggingface",
        re.compile(r"huggingface\.co/(?:spaces/)?([\w.-]+)/([\w.-]+)" + _TAIL, re.IGNORECASE),
    ),
)

HOST_DOMAINS: Final[dict[CodeHost, str]] = {
    "github": "github.com",
    "gitlab": "gitlab.com",
    "huggingface": "huggingface.co",
}


def extract_code_links(text: str) -> tuple[CodeLink, ...]:
    """Extract canonical repo links, order-preserving and deduplicated.

    Args:
        text: Abstract plus comment text.

    Returns:
        Code links with `.git` suffixes stripped and trailing punctuation
        excluded by the tail lookahead.
    """
    found: dict[str, CodeLink] = {}
    for host, pattern in HOST_PATTERNS:
        for match in pattern.finditer(text):
            owner, repo = match.group(1), match.group(2)
            repo = repo.rstrip(".").removesuffix(".git").rstrip(".")
            if not repo:
                continue
            url = f"https://{HOST_DOMAINS[host]}/{owner}/{repo}"
            found.setdefault(url.lower(), CodeLink(url=url, host=host, owner=owner, repo=repo))
    return tuple(found.values())
