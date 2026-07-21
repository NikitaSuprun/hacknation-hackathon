"""CLI entry: python -m scrapers.hacknation run [--since] [--fixtures] [--dry-run] [--no-cvs]."""

import time
import uuid
from datetime import UTC, datetime
from typing import Final

import typer
from databricks.sdk import WorkspaceClient

from scrapers.common.cli import resolve_since
from scrapers.common.http import HttpClient, Timing, TokenBucket
from scrapers.common.log import configure_logging
from scrapers.common.settings import load_scraper_settings, offline_scraper_settings
from scrapers.common.sink import DEFAULT_CATALOG, build_deps
from scrapers.hacknation.client import BUCKET, HacknationClient, cookie_headers
from scrapers.hacknation.cv import CV_BUCKET
from scrapers.hacknation.pipeline import PipelineDeps, run_pipeline
from scrapers.hacknation.replay import fixture_routes
from scrapers.hacknation.scraper import SOURCE
from tools.settings import load_databricks_settings

API_RATE_PER_SEC: Final[float] = 2.0  # gentle on the two Netlify functions
CV_RATE_PER_SEC: Final[float] = 1.0  # gentler still on third-party CV hosts

app: Final[typer.Typer] = typer.Typer(add_completion=False)


@app.callback()
def main() -> None:
    """Hack Nation showcase scraper (people, projects, CVs, PSRs)."""


def _workspace() -> WorkspaceClient:
    # Same construction as tools.db: service-principal M2M OAuth.
    settings = load_databricks_settings()
    return WorkspaceClient(
        host=settings.host, client_id=settings.client_id, client_secret=settings.client_secret
    )


@app.command()
def run(
    *,
    since: str | None = None,
    limit: int = 0,
    fixtures: bool = False,
    dry_run: bool = False,
    cvs: bool = True,
) -> None:
    """Run the full pipeline: bronze sweep, CVs, PSR merge, silver projects."""
    configure_logging()
    offline = fixtures and dry_run
    settings = offline_scraper_settings() if offline else load_scraper_settings()
    transport = fixture_routes() if fixtures else None
    timing = Timing(
        clock=time.monotonic, sleep=(lambda _s: None) if transport is not None else time.sleep
    )
    http = HttpClient(
        user_agent=settings.user_agent,
        headers=cookie_headers(),
        buckets={
            BUCKET: TokenBucket(API_RATE_PER_SEC, 1.0, timing=timing),
            CV_BUCKET: TokenBucket(CV_RATE_PER_SEC, 1.0, timing=timing),
        },
        transport=transport,
        timing=timing,
    )
    deps = build_deps(SOURCE, dry_run=dry_run)
    summary = run_pipeline(
        PipelineDeps(
            client=HacknationClient(http),
            http=http,
            runner=deps,
            since=resolve_since(since),
            limit=limit,
            clock=lambda: datetime.now(UTC),
            run_id=uuid.uuid4().hex,
            log=deps.log,
            catalog=DEFAULT_CATALOG,
            fetch_cvs=cvs,
            workspace=_workspace() if deps.warehouse is not None and cvs else None,
        )
    )
    typer.echo(
        f"{SOURCE}: people={summary.people} projects={summary.projects} "
        f"rejects={summary.rejects} psr={summary.psr} "
        f"silver_projects={summary.silver_projects} cvs={summary.cvs}"
    )


if __name__ == "__main__":
    app()
