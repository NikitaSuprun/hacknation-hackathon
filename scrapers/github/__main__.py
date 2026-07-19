# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""CLI entry: python -m scrapers.github [--since ...] [--fixtures] [--dry-run]."""

import time
import uuid
from datetime import UTC, datetime
from typing import Final

from scrapers.common.base import RunnableScraper
from scrapers.common.cli import ScraperContext, build_app
from scrapers.common.http import HttpClient, Timing, TokenBucket
from scrapers.common.log import get_logger
from scrapers.common.settings import require_key
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
        )
    )


app: Final = build_app(SOURCE, _make_scraper, fixture_routes)

if __name__ == "__main__":
    app()
