# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""HTTP access to the two public JSON endpoints of the Hack Nation showcase.

Netlify answers unknown routes with the SPA's index.html and HTTP 200, so
every response is content-type guarded before JSON decoding; throttling (429)
and server faults (5xx) are retried with exponential backoff.
"""

import os
import time
from collections.abc import Callable, Mapping
from http import HTTPStatus
from types import TracebackType
from typing import Final, Self, cast

import httpx

from contracts.models import Json

__all__ = [
    "BASE_URL",
    "COOKIE_ENV_VAR",
    "DEFAULT_PEOPLE_LIMIT",
    "DEFAULT_REQUEST_DELAY_S",
    "PEOPLE_URL",
    "PROJECT_URL_TEMPLATE",
    "TIMEOUT_S",
    "USER_AGENT",
    "HacknationClient",
    "NonJsonResponseError",
]

BASE_URL: Final[str] = "https://projects.hack-nation.ai/.netlify/functions/"
PEOPLE_URL: Final[str] = f"{BASE_URL}bff-public-people-v2"
PROJECT_URL_TEMPLATE: Final[str] = f"{BASE_URL}bff-projects-public-v2?id={{project_id}}"
USER_AGENT: Final[str] = (
    "dealflow-dealsourcing/0.1 (WS-G showcase ingest; contact: nikita.suprun@sics.ai)"
)
COOKIE_ENV_VAR: Final[str] = "HACKNATION_COOKIE"
DEFAULT_PEOPLE_LIMIT: Final[int] = 5000
DEFAULT_REQUEST_DELAY_S: Final[float] = 0.5
TIMEOUT_S: Final[float] = 30.0
_MAX_ATTEMPTS: Final[int] = 3


class NonJsonResponseError(ValueError):
    """Raised when an endpoint answers with a non-JSON body (the SPA fallback page)."""

    def __init__(self, url: str, content_type: str) -> None:
        """Name the URL and the content type it returned."""
        super().__init__(f"expected application/json from {url}, got {content_type!r}")


def _is_retryable(status_code: int) -> bool:
    """Whether the status warrants another attempt (throttling or server fault)."""
    return (
        status_code == HTTPStatus.TOO_MANY_REQUESTS
        or status_code >= HTTPStatus.INTERNAL_SERVER_ERROR
    )


class HacknationClient:
    """One polite HTTP session over the public people and project endpoints."""

    _client: Final[httpx.Client]
    _request_delay_s: Final[float]
    _sleep: Final[Callable[[float], None]]

    def __init__(
        self,
        transport: httpx.BaseTransport | None = None,
        request_delay_s: float = DEFAULT_REQUEST_DELAY_S,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """Open the session; tests inject a MockTransport and a no-op sleep."""
        headers = {"User-Agent": USER_AGENT}
        # Login is optional (the data is public); a cookie only widens fields.
        cookie = os.environ.get(COOKIE_ENV_VAR, "")
        if cookie:
            headers["Cookie"] = cookie
        self._client = httpx.Client(
            base_url=BASE_URL, headers=headers, timeout=TIMEOUT_S, transport=transport
        )
        self._request_delay_s = request_delay_s
        self._sleep = sleep

    def __enter__(self) -> Self:
        """Return self; the session is already open."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Close the underlying httpx session."""
        self.close()

    def close(self) -> None:
        """Close the underlying httpx session."""
        self._client.close()

    def people(self, limit: int = DEFAULT_PEOPLE_LIMIT) -> Json:
        """Fetch the whole public people directory in one request.

        Args:
            limit: Page size; the default comfortably exceeds the published
                profile count (~1000).

        Returns:
            The full response body; callers unwrap "data".
        """
        return self._json_body(self._get("bff-public-people-v2", {"limit": limit}))

    def project(self, project_id: str) -> Json:
        """Fetch one project detail, pausing first to stay gentle on the API.

        Args:
            project_id: The project UUID (from a contributions entry).

        Returns:
            The full response body; callers unwrap "data".
        """
        self._sleep(self._request_delay_s)
        return self._json_body(self._get("bff-projects-public-v2", {"id": project_id}))

    def _get(self, path: str, params: Mapping[str, str | int]) -> httpx.Response:
        """GET with up to three attempts; 429/5xx back off 2**attempt seconds."""
        response = self._client.get(path, params=params)
        for attempt in range(_MAX_ATTEMPTS - 1):
            if not _is_retryable(response.status_code):
                break
            self._sleep(2.0**attempt)
            response = self._client.get(path, params=params)
        response.raise_for_status()
        return response

    def _json_body(self, response: httpx.Response) -> Json:
        """Decode a JSON body, refusing the Netlify SPA fallback page.

        Args:
            response: The already status-checked endpoint response.

        Returns:
            The parsed body.

        Raises:
            NonJsonResponseError: If the content-type is not application/json;
                Netlify serves index.html with HTTP 200 for unknown routes.
        """
        content_type = response.headers.get("content-type", "")
        if content_type.partition(";")[0].strip().lower() != "application/json":
            raise NonJsonResponseError(str(response.url), content_type)
        # httpx types .json() as Any; this API's bodies are plain JSON values.
        return cast("Json", response.json())
