# Copyright (c) 2026 Venture Hunt. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Fixture replay routes for the Hack Nation client.

The committed wire fixtures include one project id (hnp-spa-01) that answers
the Netlify SPA index page with HTTP 200, so every replay run exercises the
content-type guard exactly as a live run would.
"""

import re
from pathlib import Path
from typing import Final

import httpx

from scrapers.common.fixtures import FixtureRoute, build_mock_transport, json_body, text_body

FIXTURE_DIR: Final[Path] = Path(__file__).resolve().parent / "fixtures"
SPA_PROJECT_ID: Final[str] = "hnp-spa-01"


def fixture_routes() -> list[FixtureRoute]:
    """The replay rules for both endpoints (first match wins).

    Returns:
        Routes for the people listing, both project details, and the
        SPA-fallback project.
    """
    return [
        FixtureRoute(
            "GET",
            re.compile(r"bff-public-people-v2"),
            json_body(FIXTURE_DIR / "people.json"),
        ),
        FixtureRoute(
            "GET",
            re.compile(r"bff-projects-public-v2\?id=hnp-grasp-01$"),
            json_body(FIXTURE_DIR / "project-hnp-grasp-01.json"),
        ),
        FixtureRoute(
            "GET",
            re.compile(r"bff-projects-public-v2\?id=hnp-voice-01$"),
            json_body(FIXTURE_DIR / "project-hnp-voice-01.json"),
        ),
        FixtureRoute(
            "GET",
            re.compile(r"bff-projects-public-v2"),
            text_body(FIXTURE_DIR / "spa-fallback.html", "text/html; charset=utf-8"),
        ),
    ]


def fixture_transport() -> httpx.MockTransport:
    """The assembled replay transport.

    Returns:
        A transport for HttpClient's transport parameter.
    """
    return build_mock_transport(fixture_routes())
