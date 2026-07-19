# Copyright (c) 2026 Venture Hunt. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""CLI entry: python -m sources.hacknation [--fixtures] [--dry-run] [--limit] [--catalog].

Deliberately not built on the shared BaseScraper runner (the source is two
endpoints and one pass); it composes the same shared pieces directly -
HttpClient with a gentle token bucket, build_deps for the NullSink dry-run
matrix, fixture replay at the transport layer. `--fixtures --dry-run` is the
credential-free CI path; a live run needs only Databricks credentials, the
endpoints themselves are public.
"""

import time
import uuid
from datetime import UTC, datetime
from typing import Final

import typer

from scrapers.common.http import HttpClient, Timing, TokenBucket
from scrapers.common.log import configure_logging, get_logger
from scrapers.common.settings import load_scraper_settings, offline_scraper_settings
from scrapers.common.sink import DEFAULT_CATALOG, build_deps
from sources.hacknation.client import BUCKET, RATE_PER_SEC, SOURCE, HacknationClient
from sources.hacknation.ingest import IngestContext, run_ingest
from sources.hacknation.replay import fixture_transport

app: Final[typer.Typer] = typer.Typer(add_completion=False)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _http_client(*, fixtures: bool, dry_run: bool) -> HttpClient:
    """Compose the rate-limited client (replay transport in fixtures mode)."""
    offline = fixtures and dry_run
    settings = offline_scraper_settings() if offline else load_scraper_settings()
    timing = Timing(clock=time.monotonic, sleep=(lambda _s: None) if fixtures else time.sleep)
    return HttpClient(
        user_agent=settings.user_agent,
        headers={},
        buckets={BUCKET: TokenBucket(RATE_PER_SEC, 1.0, timing=timing)},
        transport=fixture_transport() if fixtures else None,
        timing=timing,
    )


@app.command()
def run(
    *,
    fixtures: bool = False,
    dry_run: bool = False,
    limit: int = 0,
    catalog: str = DEFAULT_CATALOG,
) -> None:
    """Ingest the Hack Nation showcase into the two bronze tables."""
    configure_logging()
    deps = build_deps(SOURCE, dry_run=dry_run, catalog=catalog)
    http = _http_client(fixtures=fixtures, dry_run=dry_run)
    try:
        context = IngestContext(
            client=HacknationClient(http),
            sink=deps.sink,
            log=get_logger(SOURCE),
            clock=_utc_now,
            run_id=str(uuid.uuid4()),
            limit=limit,
        )
        report = run_ingest(context)
    finally:
        http.close()
    typer.echo(
        f"{SOURCE}: people={report.people} projects={report.projects} "
        f"skipped_non_json={report.skipped_non_json} skipped_failed={report.skipped_failed}"
    )


if __name__ == "__main__":
    app()
