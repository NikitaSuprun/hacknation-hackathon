"""Access to the two public JSON endpoints of the Hack Nation showcase.

The shared HttpClient owns rate limiting and retries; what stays local is the
content-type guard, because Netlify answers unknown routes with the SPA's
index.html and HTTP 200 — without the guard that page would parse as garbage
instead of failing loudly.
"""

import json
import os
from collections.abc import Mapping
from typing import Final, cast

from contracts.models import Json
from scrapers.common.http import HttpClient

__all__ = [
    "BASE_URL",
    "BUCKET",
    "COOKIE_ENV_VAR",
    "DEFAULT_PEOPLE_LIMIT",
    "PEOPLE_URL",
    "PROJECT_URL_TEMPLATE",
    "HacknationClient",
    "NonJsonResponseError",
    "cookie_headers",
]

BASE_URL: Final[str] = "https://projects.hack-nation.ai/.netlify/functions/"
PEOPLE_URL: Final[str] = f"{BASE_URL}bff-public-people-v2"
PROJECT_URL_TEMPLATE: Final[str] = f"{BASE_URL}bff-projects-public-v2?id={{project_id}}"
BUCKET: Final[str] = "hacknation"
COOKIE_ENV_VAR: Final[str] = "HACKNATION_COOKIE"
DEFAULT_PEOPLE_LIMIT: Final[int] = 5000
_JSON_CONTENT_TYPE: Final[str] = "application/json"


class NonJsonResponseError(ValueError):
    """Raised when an endpoint answers with a non-JSON body (the SPA fallback page)."""

    def __init__(self, url: str, content_type: str) -> None:
        """Name the URL and the content type it returned."""
        super().__init__(f"expected application/json from {url}, got {content_type!r}")


def cookie_headers() -> dict[str, str]:
    """Optional Cookie header from the environment.

    Login is optional (the data is public); a cookie only widens fields.

    Returns:
        {"Cookie": ...} when HACKNATION_COOKIE is set, else empty.
    """
    cookie = os.environ.get(COOKIE_ENV_VAR, "")
    return {"Cookie": cookie} if cookie else {}


def _content_type(headers: Mapping[str, str]) -> str:
    """The content-type header value, looked up case-insensitively."""
    for key, value in headers.items():
        if key.lower() == "content-type":
            return value
    return ""


class HacknationClient:
    """The people and project lookups, riding the shared HttpClient (bucket 'hacknation')."""

    def __init__(self, http: HttpClient) -> None:
        """Bind to the shared client; buckets and headers are composed there."""
        self._http: Final[HttpClient] = http

    def people(self, limit: int = DEFAULT_PEOPLE_LIMIT) -> Json:
        """Fetch the whole public people directory in one request.

        Args:
            limit: Page size; the default comfortably exceeds the published
                profile count (~1000).

        Returns:
            The full response body; callers unwrap "data".
        """
        return self._json_body(PEOPLE_URL, params={"limit": str(limit)})

    def project(self, project_id: str) -> Json:
        """Fetch one project detail.

        Args:
            project_id: The project UUID (from a contributions entry).

        Returns:
            The full response body; callers unwrap "data".
        """
        return self._json_body(PROJECT_URL_TEMPLATE.format(project_id=project_id))

    def _json_body(self, url: str, params: Mapping[str, str] | None = None) -> Json:
        """GET and decode a JSON body, refusing the Netlify SPA fallback page.

        Args:
            url: Absolute request URL.
            params: Query parameters.

        Returns:
            The parsed body.

        Raises:
            NonJsonResponseError: If the content-type is not application/json;
                Netlify serves index.html with HTTP 200 for unknown routes.
        """
        response = self._http.get(url, bucket=BUCKET, params=params, accept=_JSON_CONTENT_TYPE)
        content_type = _content_type(response.headers)
        if content_type.partition(";")[0].strip().lower() != _JSON_CONTENT_TYPE:
            raise NonJsonResponseError(url, content_type)
        # json.loads returns Any; this API's bodies are plain JSON values.
        return cast("Json", json.loads(response.body))
