# Copyright (c) 2026 Venture Hunt. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""The SPA fallback: client-side routes resolve, missing assets still 404.

The deployed image serves the React bundle from app/static same-origin, and
BrowserRouter paths only exist in the client router — so the static mount has
to hand them the shell instead of 404ing a refreshed or shared link.
"""

from typing import Final

import pytest

from tests.app.conftest import AppClient

CLIENT_ROUTES: Final[tuple[str, ...]] = ("/thesis", "/login", "/chosen", "/t/thesis-1/ranking")
MISSING_ASSETS: Final[tuple[str, ...]] = ("/assets/absent.js", "/absent.png", "/fonts/absent.woff2")


@pytest.mark.parametrize("path", CLIENT_ROUTES)
def test_client_route_serves_the_shell(client: AppClient, path: str) -> None:
    """A BrowserRouter path returns the SPA shell, not a 404."""
    response = client.get(path)
    assert response.status_code == 200
    assert "<html" in response.text.lower()


@pytest.mark.parametrize("path", MISSING_ASSETS)
def test_missing_asset_stays_a_404(client: AppClient, path: str) -> None:
    """A path with a file extension must not fall back to the HTML shell.

    Serving HTML for a missing bundle makes the browser report a JavaScript
    syntax error instead of the actual missing file.
    """
    assert client.get(path).status_code == 404


def test_index_is_served_at_the_root(client: AppClient) -> None:
    """The root still resolves through the normal static path."""
    response = client.get("/")
    assert response.status_code == 200
    assert "<html" in response.text.lower()


def test_unauthenticated_api_path_is_not_swallowed_by_the_fallback(client: AppClient) -> None:
    """/v1 stays gated: the session 401 must win over the SPA fallback."""
    assert client.get("/v1/thesis").status_code == 401
