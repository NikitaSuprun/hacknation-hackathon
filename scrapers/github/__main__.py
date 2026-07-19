# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""CLI entry: python -m scrapers.github [--since ...] [--fixtures] [--dry-run].

Targeted hydration: `--repos owner/name,...` scrapes exactly those repos, and
`--from-hacknation` expands to every repo referenced by a Hack Nation project
already ingested into bronze — hackathon repos never surface via the
star-based discovery window, so this is how their GitHub signal lands.
"""

import re
import time
import uuid
from datetime import UTC, datetime
from typing import Final

from scrapers.common.base import RunnableScraper
from scrapers.common.cli import HACKNATION_REPOS_MARKER, ScraperContext, build_app
from scrapers.common.http import HttpClient, Timing, TokenBucket
from scrapers.common.log import get_logger
from scrapers.common.settings import require_key
from scrapers.common.state import SqlRunner, require_identifier
from scrapers.github.client_gql import GithubGraphql
from scrapers.github.client_rest import API_VERSION_HEADER, GithubRest
from scrapers.github.normalize import SOURCE
from scrapers.github.replay import fixture_routes
from scrapers.github.scraper import (
    GithubDeps,
    GithubScraper,
    NullReadback,
    ReadbackReader,
    WarehouseReadback,
)

SEARCH_RATE_PER_SEC: Final[float] = 0.45  # ~27/min under the 30/min search budget
CORE_RATE_PER_SEC: Final[float] = 1.2  # well under REST 5000/hr
GRAPHQL_RATE_PER_SEC: Final[float] = 0.5


def _buckets(timing: Timing) -> dict[str, TokenBucket]:
    return {
        "search": TokenBucket(SEARCH_RATE_PER_SEC, 1.0, timing=timing),
        "core": TokenBucket(CORE_RATE_PER_SEC, 5.0, timing=timing),
        "graphql": TokenBucket(GRAPHQL_RATE_PER_SEC, 2.0, timing=timing),
    }


GITHUB_URL_RE: Final[re.Pattern[str]] = re.compile(
    r"github\.com/([\w.-]+)/([\w.-]+?)(?:\.git)?(?:[/?#]|$)", re.IGNORECASE
)


class HacknationRepoSourceError(RuntimeError):
    """--from-hacknation needs warehouse access to read the project URLs."""

    def __init__(self) -> None:
        """Explain the requirement."""
        super().__init__(
            "--from-hacknation reads bronze.hacknation_projects_raw and needs a live "
            "warehouse run (drop --dry-run, keep Databricks credentials in .env)"
        )


def full_name(entry: str) -> str | None:
    """The 'owner/name' for a repo URL or bare name.

    Args:
        entry: A github.com URL or an 'owner/name' string.

    Returns:
        The full name, or None when the entry names no repo.
    """
    match = GITHUB_URL_RE.search(entry)
    if match is not None:
        return f"{match.group(1)}/{match.group(2)}"
    return entry if "/" in entry else None


def hacknation_repos(runner: SqlRunner, catalog: str) -> list[str]:
    """Repo full names referenced by ingested Hack Nation projects.

    Args:
        runner: The warehouse query seam.
        catalog: The catalog holding bronze (validated as an identifier).

    Returns:
        Deduplicated 'owner/name' values parsed from each project githubUrl.
    """
    rows = runner.execute(
        "SELECT DISTINCT CAST(payload:githubUrl AS STRING) "  # noqa: S608 - catalog guarded by require_identifier; no user input
        f"FROM {require_identifier(catalog)}.bronze.hacknation_projects_raw "
        "WHERE payload:githubUrl IS NOT NULL"
    )
    names = [full_name(str(row[0])) for row in rows if row[0] is not None]
    return [name for name in names if name is not None]


def resolve_repos(context: ScraperContext) -> tuple[str, ...]:
    """Expand the --repos/--from-hacknation flags into repo full names.

    Args:
        context: The run context (repo flags, warehouse, catalog).

    Returns:
        Deduplicated 'owner/name' values, order preserved.

    Raises:
        HacknationRepoSourceError: If the Hack Nation marker is present but
            the run has no warehouse to read project URLs from.
    """
    resolved: list[str] = []
    for entry in context.repos:
        if entry == HACKNATION_REPOS_MARKER:
            if context.warehouse is None:
                raise HacknationRepoSourceError
            resolved.extend(hacknation_repos(context.warehouse, context.catalog))
            continue
        name = full_name(entry)
        if name is not None:
            resolved.append(name)
    return tuple(dict.fromkeys(resolved))


def _make_scraper(context: ScraperContext) -> RunnableScraper:
    replaying = context.transport is not None
    token = context.settings.github_token or ("fixture-token" if replaying else None)
    timing = Timing(clock=time.monotonic, sleep=(lambda _s: None) if replaying else time.sleep)
    http = HttpClient(
        user_agent=context.settings.user_agent,
        headers={
            "Authorization": f"Bearer {require_key(token, 'GITHUB_TOKEN')}",
            **API_VERSION_HEADER,
        },
        buckets=_buckets(timing),
        transport=context.transport,
        timing=timing,
    )
    log = get_logger(SOURCE)
    readback: ReadbackReader = (
        WarehouseReadback(context.warehouse, context.catalog)
        if context.warehouse is not None
        else NullReadback()
    )
    return GithubScraper(
        GithubDeps(
            rest=GithubRest(http),
            gql=GithubGraphql(http, log),
            readback=readback,
            since=context.since,
            limit=context.limit,
            clock=lambda: datetime.now(UTC),
            run_id=uuid.uuid4().hex,
            log=log,
            explicit_repos=resolve_repos(context),
        )
    )


app: Final = build_app(SOURCE, _make_scraper, fixture_routes)

if __name__ == "__main__":
    app()
