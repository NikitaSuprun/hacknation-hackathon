# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""CLI composition: one place that wires settings, transport, deps, and runner.

Per-source packages provide a factory from ScraperContext to a scraper; this
module owns the shared flag surface (--since, --limit, --fixtures, --dry-run)
and the mode matrix. `--fixtures --dry-run` is the credential-free CI path.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Final

import httpx
import typer

from contracts.models import RunResult
from scrapers.common.base import RunnableScraper, execute_run
from scrapers.common.log import configure_logging
from scrapers.common.settings import (
    ScraperSettings,
    load_scraper_settings,
    offline_scraper_settings,
)
from scrapers.common.sink import DEFAULT_CATALOG, build_deps
from tools.warehouse import Warehouse

DEFAULT_WINDOW_DAYS: Final[int] = 30


@dataclass(frozen=True, slots=True)
class ScraperContext:
    """Everything a per-source factory needs to assemble its scraper."""

    settings: ScraperSettings
    transport: httpx.BaseTransport | None
    warehouse: Warehouse | None
    limit: int
    since: date


MakeScraper = Callable[[ScraperContext], RunnableScraper]
TransportFactory = Callable[[], httpx.BaseTransport]


@dataclass(frozen=True, slots=True)
class RunOptions:
    """The shared CLI flag surface, resolved."""

    since: date
    limit: int
    fixtures: bool
    dry_run: bool
    catalog: str


def resolve_since(since: str | None) -> date:
    """Parse --since, defaulting to a rolling 30-day window.

    Args:
        since: ISO date string from the CLI, or None.

    Returns:
        The backfill start date.
    """
    if since is not None:
        return date.fromisoformat(since)
    return datetime.now(UTC).date() - timedelta(days=DEFAULT_WINDOW_DAYS)


def run_scraper(
    source: str,
    make_scraper: MakeScraper,
    fixture_transport: TransportFactory,
    options: RunOptions,
) -> RunResult:
    """Assemble dependencies per the mode matrix and execute one run.

    Args:
        source: The scraper source name.
        make_scraper: Factory building the scraper from its context.
        fixture_transport: Factory for the replay transport (fixtures mode).
        options: Resolved CLI flags.

    Returns:
        The run summary.
    """
    configure_logging()
    offline = options.fixtures and options.dry_run
    settings = offline_scraper_settings() if offline else load_scraper_settings()
    deps = build_deps(source, dry_run=options.dry_run, catalog=options.catalog)
    context = ScraperContext(
        settings=settings,
        transport=fixture_transport() if options.fixtures else None,
        warehouse=deps.warehouse,
        limit=options.limit,
        since=options.since,
    )
    result = execute_run(make_scraper(context), deps, options.since)
    deps.log.info(
        "run complete",
        source=result.source,
        items_upserted=result.items_upserted,
        rejects=result.rejects,
    )
    return result


def build_app(
    source: str, make_scraper: MakeScraper, fixture_transport: TransportFactory
) -> typer.Typer:
    """Build the single-command typer app shared by simple scrapers.

    Args:
        source: The scraper source name.
        make_scraper: Factory building the scraper from its context.
        fixture_transport: Factory for the replay transport.

    Returns:
        The typer application.
    """
    app = typer.Typer(add_completion=False)

    @app.command()
    def run(  # pyright: ignore[reportUnusedFunction] - typer registers the command via the decorator
        *,
        since: str | None = None,
        limit: int = 0,
        fixtures: bool = False,
        dry_run: bool = False,
    ) -> None:
        """Run the scraper (fetch, normalize, upsert, advance cursor)."""
        result = run_scraper(
            source,
            make_scraper,
            fixture_transport,
            RunOptions(
                since=resolve_since(since),
                limit=limit,
                fixtures=fixtures,
                dry_run=dry_run,
                catalog=DEFAULT_CATALOG,
            ),
        )
        typer.echo(
            f"{result.source}: items_upserted={result.items_upserted} rejects={result.rejects}"
        )

    return app
