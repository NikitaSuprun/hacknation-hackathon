# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""The Hack Nation showcase client: two public JSON endpoints, no login.

Netlify SPA-fallbacks unknown routes to index.html with HTTP 200, so every
response is content-type-guarded before parsing: a non-JSON body raises the
typed NotJsonResponseError instead of silently normalizing an HTML page.
"""

from typing import Final

from contracts.models import Json
from scrapers.common.http import HttpClient
from scrapers.common.jsonutil import as_mapping, get_map
from scrapers.common.models import FetchedResponse

SOURCE: Final[str] = "hacknation"
BUCKET: Final[str] = "hacknation"
RATE_PER_SEC: Final[float] = 1.0
PEOPLE_URL: Final[str] = "https://projects.hack-nation.ai/.netlify/functions/bff-public-people-v2"
PROJECT_URL: Final[str] = (
    "https://projects.hack-nation.ai/.netlify/functions/bff-projects-public-v2"
)
DEFAULT_PEOPLE_LIMIT: Final[int] = 5000
JSON_CONTENT_TYPE: Final[str] = "application/json"


class NotJsonResponseError(RuntimeError):
    """The endpoint answered a non-JSON body (the Netlify SPA fallback)."""

    def __init__(self, url: str, content_type: str) -> None:
        """Name the URL and the offending content type."""
        super().__init__(f"expected application/json from {url}, got {content_type!r}")
        self.url: Final[str] = url


def _require_json(response: FetchedResponse, url: str) -> None:
    """Raise unless the response declares a JSON content type."""
    content_type = ""
    for name, value in response.headers.items():
        if name.lower() == "content-type":
            content_type = value
            break
    if JSON_CONTENT_TYPE not in content_type.lower():
        raise NotJsonResponseError(url, content_type)


class HacknationClient:
    """Typed access to bff-public-people-v2 and bff-projects-public-v2."""

    def __init__(self, http: HttpClient) -> None:
        """Bind the shared rate-limited HTTP client."""
        self._http: Final[HttpClient] = http

    def people(self, limit: int = DEFAULT_PEOPLE_LIMIT) -> dict[str, Json]:
        """Fetch the full people listing (one request).

        Args:
            limit: The `limit` query parameter (the API caps server-side).

        Returns:
            The response's `data` object: `{people: [...],
            contributionsByUserId: {...}}` (a non-JSON answer raises
            NotJsonResponseError).
        """
        response = self._http.get(
            PEOPLE_URL,
            bucket=BUCKET,
            params={"limit": str(limit)},
            accept=JSON_CONTENT_TYPE,
        )
        _require_json(response, PEOPLE_URL)
        return get_map(as_mapping(response.json()), "data")

    def project(self, project_id: str) -> dict[str, Json]:
        """Fetch one project detail.

        Args:
            project_id: The showcase project id.

        Returns:
            The response's `data` object (title, team, githubUrl, structured).
            A non-JSON answer raises NotJsonResponseError — an unknown id
            falls back to the SPA index page.
        """
        response = self._http.get(
            PROJECT_URL,
            bucket=BUCKET,
            params={"id": project_id},
            accept=JSON_CONTENT_TYPE,
        )
        _require_json(response, f"{PROJECT_URL}?id={project_id}")
        return get_map(as_mapping(response.json()), "data")
