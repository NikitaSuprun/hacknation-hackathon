# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Bot filtering and the core-contributor rule (the G2 selection contract)."""

import math
from typing import Final

from scrapers.github.models import ContributorStat

BOT_DENYLIST: Final[frozenset[str]] = frozenset(
    {
        "dependabot",
        "renovate",
        "github-actions",
        "greenkeeper",
        "snyk-bot",
        "imgbot",
        "allcontributors",
        "codecov",
        "pre-commit-ci",
        "web-flow",
        "weblate",
    }
)

CORE_MIN_CONTRIBUTIONS: Final[int] = 3
CORE_SHARE: Final[float] = 0.05
CORE_MAX_RANK: Final[int] = 10
CORE_CAP: Final[int] = 5


def is_bot(login: str, user_type: str) -> bool:
    """Whether a contributor entry is a bot (type, [bot] suffix, or denylist).

    Args:
        login: The contributor login.
        user_type: The REST `type` field ('User' or 'Bot').

    Returns:
        True when the entry must never be harvested.
    """
    if user_type == "Bot" or login.endswith("[bot]"):
        return True
    return login.lower().removesuffix("[bot]") in BOT_DENYLIST


def core_contributors(stats: list[ContributorStat]) -> list[ContributorStat]:
    """Select the core set: threshold by share, rank cap, then hard cap.

    Core iff contributions >= max(3, ceil(0.05 * repo_total)) AND rank <= 10,
    keeping at most 5 per repo. Bots are dropped before the total is computed
    so bot-inflated repos do not distort the share threshold.

    Args:
        stats: REST contributor entries in rank order (most contributions first).

    Returns:
        The core contributors, best rank first.
    """
    humans = [stat for stat in stats if not is_bot(stat.login, stat.user_type)]
    ranked = sorted(humans, key=lambda stat: stat.contributions, reverse=True)
    total = sum(stat.contributions for stat in ranked)
    threshold = max(CORE_MIN_CONTRIBUTIONS, math.ceil(CORE_SHARE * total))
    core = [
        stat
        for rank, stat in enumerate(ranked[:CORE_MAX_RANK], start=1)
        if stat.contributions >= threshold and rank <= CORE_MAX_RANK
    ]
    return core[:CORE_CAP]
