"""Fixture replay for the Hack Nation scraper (the --fixtures transport).

The people file answers the directory sweep, project files are routed by the
`id` query parameter, and the committed PDF answers the one fixture cvUrl. An
unknown project id answers the Netlify SPA fallback (200 text/html), so replay
exercises the client's content-type guard exactly like production would.
"""

import re
from pathlib import Path
from typing import Final

import httpx

from scrapers.common.fixtures import FixtureRoute, build_mock_transport, json_body, text_body

FIXTURES_DIR: Final[Path] = Path(__file__).parent / "fixtures"
CV_PDF: Final[Path] = FIXTURES_DIR / "cv_hn_selin_0003.pdf"
SPA_FALLBACK: Final[bytes] = b"<!doctype html><html><body>hack nation</body></html>"


def _project(request: httpx.Request) -> httpx.Response:
    project_id = request.url.params.get("id", "")
    path = FIXTURES_DIR / f"project_{project_id}.json"
    if not path.is_file():
        return httpx.Response(
            200, content=SPA_FALLBACK, headers={"Content-Type": "text/html; charset=UTF-8"}
        )
    return httpx.Response(
        200, content=path.read_bytes(), headers={"Content-Type": "application/json"}
    )


def fixture_routes() -> httpx.MockTransport:
    """The replay transport covering every endpoint the pipeline hits.

    Returns:
        A MockTransport for HttpClient (unmatched requests answer 418).
    """
    return build_mock_transport(
        (
            FixtureRoute(
                "GET", re.compile(r"bff-public-people-v2"), json_body(FIXTURES_DIR / "people.json")
            ),
            FixtureRoute("GET", re.compile(r"bff-projects-public-v2"), _project),
            FixtureRoute(
                "GET",
                re.compile(r"cdn\.hack-nation\.ai/cv/"),
                text_body(CV_PDF, "application/pdf"),
            ),
        )
    )
