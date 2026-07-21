"""GitHub REST endpoints: repo search, raw READMEs, contributor lists.

Search runs on its own bucket (separate 30 req/min budget); README and
contributors ride the core budget with ETag conditional requests so daily
refetches come back 304 for free.
"""

from datetime import date
from typing import Final

from contracts.models import Json
from scrapers.common.http import HttpClient
from scrapers.common.jsonutil import as_list, as_mapping, get_int
from scrapers.common.models import FetchedResponse

API_BASE: Final[str] = "https://api.github.com"
SEARCH_BUCKET: Final[str] = "search"
CORE_BUCKET: Final[str] = "core"
SEARCH_PAGE_SIZE: Final[int] = 100
MIN_STARS: Final[int] = 10
NOT_FOUND_STATUS: Final[int] = 404
README_ACCEPT: Final[str] = "application/vnd.github.raw+json"
API_VERSION_HEADER: Final[dict[str, str]] = {"X-GitHub-Api-Version": "2022-11-28"}


def search_query(start: date, end: date) -> str:
    """The created-window search qualifier string.

    Args:
        start: Window start (inclusive).
        end: Window end (inclusive).

    Returns:
        The `q` parameter value.
    """
    return f"created:{start.isoformat()}..{end.isoformat()} stars:>={MIN_STARS}"


class GithubRest:
    """Thin typed wrappers over the REST endpoints WS-A uses."""

    def __init__(self, http: HttpClient) -> None:
        """Ride one shared HttpClient (buckets: 'search', 'core')."""
        self._http: Final[HttpClient] = http

    def search_total(self, start: date, end: date) -> int:
        """Probe the result count for a created window (1 cheap request).

        Args:
            start: Window start.
            end: Window end.

        Returns:
            The reported total_count.
        """
        response = self._http.get(
            f"{API_BASE}/search/repositories",
            bucket=SEARCH_BUCKET,
            params={"q": search_query(start, end), "per_page": "1"},
        )
        return get_int(as_mapping(response.json()), "total_count") or 0

    def search_page(self, start: date, end: date, page: int) -> list[dict[str, Json]]:
        """One page of the created-window search, most-starred first.

        Args:
            start: Window start.
            end: Window end.
            page: 1-based page number.

        Returns:
            The raw search items.
        """
        response = self._http.get(
            f"{API_BASE}/search/repositories",
            bucket=SEARCH_BUCKET,
            params={
                "q": search_query(start, end),
                "sort": "stars",
                "order": "desc",
                "per_page": str(SEARCH_PAGE_SIZE),
                "page": str(page),
            },
        )
        return get_list_of_maps(response)

    def repo(self, full_name: str) -> dict[str, Json] | None:
        """Fetch one repo's REST metadata (targeted hydration path).

        Args:
            full_name: 'owner/repo'.

        Returns:
            The repo object, or None when the repo does not exist.
        """
        response = self._http.get(
            f"{API_BASE}/repos/{full_name}",
            bucket=CORE_BUCKET,
            allow=frozenset({NOT_FOUND_STATUS}),
        )
        if response.status == NOT_FOUND_STATUS:
            return None
        return as_mapping(response.json())

    def readme(self, full_name: str, *, etag: str | None) -> FetchedResponse:
        """Fetch the raw README (conditional when an ETag is known).

        Args:
            full_name: 'owner/repo'.
            etag: Prior ETag, or None for an unconditional fetch.

        Returns:
            The response; 404 (no README) and 304 surface to the caller.
        """
        return self._http.get(
            f"{API_BASE}/repos/{full_name}/readme",
            bucket=CORE_BUCKET,
            accept=README_ACCEPT,
            etag=etag,
            allow=frozenset({404}),
        )

    def contributors(self, full_name: str, *, etag: str | None) -> FetchedResponse:
        """Fetch the top contributors (conditional when an ETag is known).

        Args:
            full_name: 'owner/repo'.
            etag: Prior ETag, or None for an unconditional fetch.

        Returns:
            The response; 404/202/204 (missing/computing/empty) surface.
        """
        return self._http.get(
            f"{API_BASE}/repos/{full_name}/contributors",
            bucket=CORE_BUCKET,
            params={"per_page": "100", "anon": "false"},
            etag=etag,
            allow=frozenset({404}),
        )


def get_list_of_maps(response: FetchedResponse) -> list[dict[str, Json]]:
    """Decode a search response body into its item mappings.

    Args:
        response: The search-page response.

    Returns:
        The item objects (non-mappings dropped).
    """
    body = as_mapping(response.json())
    return [as_mapping(item) for item in as_list(body.get("items"))]
