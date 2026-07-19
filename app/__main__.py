# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""The app CLI: `python -m app serve [--fixtures]` runs the whole loop locally.

Fixtures mode needs zero credentials (JSONL data, recorded mail, scripted
LLM); live mode reads the Databricks .env and optionally RESEND_API_KEY and
APP_PASSWORD.
"""

from typing import Final

import typer
import uvicorn

from app.api import create_app
from app.deps import build_fixture_deps, build_live_deps
from scrapers.common.sink import DEFAULT_CATALOG

DEFAULT_PORT: Final[int] = 8799
DEFAULT_HOST: Final[str] = "127.0.0.1"

cli: Final[typer.Typer] = typer.Typer(add_completion=False, no_args_is_help=True)


@cli.callback()
def main() -> None:
    """The dealflow app CLI (see `serve`)."""


@cli.command()
def serve(
    *,
    fixtures: bool = False,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    catalog: str = DEFAULT_CATALOG,
) -> None:
    """Serve the UI and the /v1 proxy.

    Args:
        fixtures: Zero-credential demo mode over fixtures/data.
        host: Bind address.
        port: Bind port.
        catalog: Target catalog for live mode.
    """
    base_url = f"http://{host}:{port}"
    deps = (
        build_fixture_deps(base_url=base_url)
        if fixtures
        else build_live_deps(base_url=base_url, catalog=catalog)
    )
    typer.echo(f"dealflow app on {base_url} (fixtures={fixtures}, catalog={catalog})")
    uvicorn.run(create_app(deps), host=host, port=port)


if __name__ == "__main__":
    cli()
