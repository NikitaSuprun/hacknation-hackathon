# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""CLI entry: python -m scrapers.papers {arxiv|openalex|s2|pwc-load} [...]."""

import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

import typer

from scrapers.common.base import RunnableScraper
from scrapers.common.cli import RunOptions, ScraperContext, resolve_since, run_scraper
from scrapers.common.http import HttpClient, Timing, TokenBucket
from scrapers.common.log import configure_logging, get_logger
from scrapers.common.settings import require_key
from scrapers.common.sink import DEFAULT_CATALOG, build_deps
from scrapers.papers.arxiv_client import ARXIV_SOURCE, ArxivClient, ArxivDeps, ArxivScraper
from scrapers.papers.openalex_client import (
    OPENALEX_SOURCE,
    OpenAlexClient,
    OpenAlexDeps,
    OpenAlexScraper,
    PendingWorks,
    StaticPendingWorks,
    WarehousePendingWorks,
)
from scrapers.papers.pwc_archive import load_archive
from scrapers.papers.replay import fixture_pending, fixture_routes
from scrapers.papers.s2_client import S2_SOURCE, S2Deps, S2Scraper

ARXIV_RATE_PER_SEC: Final[float] = 1.0 / 3.0  # arXiv ToS: 1 request / 3s, single connection
OPENALEX_RATE_PER_SEC: Final[float] = 5.0
S2_RATE_PER_SEC: Final[float] = 1.0  # S2 free key: 1 RPS

app: Final[typer.Typer] = typer.Typer(add_completion=False)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _http(context: ScraperContext, bucket: str, rate: float) -> HttpClient:
    replaying = context.transport is not None
    timing = Timing(clock=time.monotonic, sleep=(lambda _s: None) if replaying else time.sleep)
    return HttpClient(
        user_agent=context.settings.user_agent,
        headers={},
        buckets={bucket: TokenBucket(rate, 1.0, timing=timing)},
        transport=context.transport,
        timing=timing,
    )


def _pending(context: ScraperContext) -> PendingWorks:
    if context.transport is not None:
        return StaticPendingWorks(fixture_pending())
    if context.warehouse is not None:
        return WarehousePendingWorks(context.warehouse, context.catalog)
    get_logger("papers").warning("no warehouse in dry-run: pending queue is empty")
    return StaticPendingWorks(())


def _make_arxiv(context: ScraperContext) -> RunnableScraper:
    return ArxivScraper(
        ArxivDeps(
            client=ArxivClient(_http(context, "arxiv", ARXIV_RATE_PER_SEC)),
            since=context.since,
            limit=context.limit,
            clock=_utc_now,
            run_id=uuid.uuid4().hex,
            log=get_logger(ARXIV_SOURCE),
        )
    )


def _make_openalex(context: ScraperContext) -> RunnableScraper:
    api_key = context.settings.openalex_api_key
    if context.transport is None:
        api_key = require_key(api_key, "OPENALEX_API_KEY")
    log = get_logger(OPENALEX_SOURCE)
    return OpenAlexScraper(
        OpenAlexDeps(
            client=OpenAlexClient(_http(context, "openalex", OPENALEX_RATE_PER_SEC), api_key, log),
            pending=_pending(context),
            since=context.since,
            limit=context.limit,
            clock=_utc_now,
            run_id=uuid.uuid4().hex,
            log=log,
        )
    )


def _make_s2(context: ScraperContext) -> RunnableScraper:
    return S2Scraper(
        S2Deps(
            http=_http(context, "s2", S2_RATE_PER_SEC),
            api_key=context.settings.s2_api_key,
            pending=_pending(context),
            since=context.since,
            limit=context.limit,
            clock=_utc_now,
            run_id=uuid.uuid4().hex,
            log=get_logger(S2_SOURCE),
        )
    )


@app.command()
def arxiv(
    *,
    since: str | None = None,
    limit: int = 0,
    fixtures: bool = False,
    dry_run: bool = False,
) -> None:
    """Scrape the arXiv spine into bronze.arxiv_papers_raw."""
    result = run_scraper(
        ARXIV_SOURCE,
        _make_arxiv,
        fixture_routes,
        RunOptions(
            since=resolve_since(since),
            limit=limit,
            fixtures=fixtures,
            dry_run=dry_run,
            catalog=DEFAULT_CATALOG,
            repos=(),
        ),
    )
    typer.echo(f"{result.source}: items_upserted={result.items_upserted} rejects={result.rejects}")


@app.command()
def openalex(
    *,
    since: str | None = None,
    limit: int = 0,
    fixtures: bool = False,
    dry_run: bool = False,
) -> None:
    """Enrich pending arXiv papers via OpenAlex into bronze.openalex_works_raw."""
    result = run_scraper(
        OPENALEX_SOURCE,
        _make_openalex,
        fixture_routes,
        RunOptions(
            since=resolve_since(since),
            limit=limit,
            fixtures=fixtures,
            dry_run=dry_run,
            catalog=DEFAULT_CATALOG,
            repos=(),
        ),
    )
    typer.echo(f"{result.source}: items_upserted={result.items_upserted} rejects={result.rejects}")


@app.command()
def s2(
    *,
    since: str | None = None,
    limit: int = 0,
    fixtures: bool = False,
    dry_run: bool = False,
) -> None:
    """Optional Semantic Scholar layer (no-op without S2_API_KEY)."""
    result = run_scraper(
        S2_SOURCE,
        _make_s2,
        fixture_routes,
        RunOptions(
            since=resolve_since(since),
            limit=limit,
            fixtures=fixtures,
            dry_run=dry_run,
            catalog=DEFAULT_CATALOG,
            repos=(),
        ),
    )
    typer.echo(f"{result.source}: items_upserted={result.items_upserted} rejects={result.rejects}")


@app.command(name="pwc-load")
def pwc_load(file: Path, *, dry_run: bool = False) -> None:
    """One-time load of the PwC archive file into bronze.paper_code_links."""
    configure_logging()
    deps = build_deps("papers.pwc", dry_run=dry_run)
    results = load_archive(file, deps.sink, _utc_now())
    inserted = sum(result.inserted for result in results)
    updated = sum(result.updated for result in results)
    skipped = sum(result.skipped_unchanged for result in results)
    typer.echo(f"paper_code_links: inserted={inserted} updated={updated} skipped={skipped}")


if __name__ == "__main__":
    app()
