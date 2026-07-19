# Copyright (c) 2026 Venture Hunt. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Rate-limited HTTP with retries: the one client every scraper goes through.

All time sources (clock, sleep) are injected so tests replay deterministically
through httpx.MockTransport with zero real waiting. Retries honor Retry-After
and the GitHub secondary-limit convention (403 with x-ratelimit-remaining: 0);
304 responses surface unretried so conditional requests stay free.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Final

import httpx

from scrapers.common.models import FetchedResponse, RateSnapshot

RETRYABLE_STATUSES: Final[frozenset[int]] = frozenset({429, 500, 502, 503, 504})
SECONDARY_LIMIT_STATUS: Final[int] = 403
NOT_MODIFIED_STATUS: Final[int] = 304
MAX_ATTEMPTS: Final[int] = 5
BACKOFF_BASE_SECONDS: Final[float] = 1.0
BACKOFF_CAP_SECONDS: Final[float] = 60.0
MIN_LIMIT_WAIT_SECONDS: Final[float] = 1.0
REQUEST_TIMEOUT_SECONDS: Final[float] = 30.0


@dataclass(frozen=True, slots=True)
class Timing:
    """Injected time sources; tests pass a fake clock and a no-op sleep."""

    clock: Callable[[], float]
    sleep: Callable[[float], None]


@dataclass(frozen=True, slots=True)
class _RequestSpec:
    method: str
    url: str
    params: Mapping[str, str] | None
    headers: Mapping[str, str] | None
    payload: Mapping[str, object] | None


class HttpStatusError(RuntimeError):
    """A response status the caller did not allow, after retries."""

    def __init__(self, status: int, url: str) -> None:
        """Name the status and URL in the message."""
        super().__init__(f"HTTP {status} for {url}")
        self.status: Final[int] = status


class TokenBucket:
    """A token bucket that sleeps (via the injected sleep) when drained."""

    def __init__(self, rate_per_sec: float, capacity: float, *, timing: Timing) -> None:
        """Start full; time sources are injected for deterministic tests."""
        self._rate: Final[float] = rate_per_sec
        self._capacity: Final[float] = capacity
        self._timing: Final[Timing] = timing
        self._tokens: float = capacity
        self._last: float = timing.clock()

    def _refill(self) -> None:
        now = self._timing.clock()
        self._tokens = min(self._capacity, self._tokens + (now - self._last) * self._rate)
        self._last = now

    def acquire(self) -> None:
        """Take one token, sleeping until one is available."""
        self._refill()
        if self._tokens < 1.0:
            self._timing.sleep((1.0 - self._tokens) / self._rate)
            self._refill()
        self._tokens -= 1.0


def backoff_delay(attempt: int) -> float:
    """Exponential backoff for attempt N (1-based), capped.

    Args:
        attempt: The attempt number that just failed.

    Returns:
        Seconds to wait before the next attempt.
    """
    return min(BACKOFF_CAP_SECONDS, BACKOFF_BASE_SECONDS * (2.0 ** (attempt - 1)))


def _is_secondary_limit(response: httpx.Response) -> bool:
    return (
        response.status_code == SECONDARY_LIMIT_STATUS
        and response.headers.get("x-ratelimit-remaining") == "0"
    )


def _is_retryable(response: httpx.Response) -> bool:
    return response.status_code in RETRYABLE_STATUSES or _is_secondary_limit(response)


def _retry_delay(response: httpx.Response, attempt: int, now: float) -> float:
    retry_after = response.headers.get("Retry-After")
    if retry_after is not None and retry_after.isdigit():
        return max(float(retry_after), MIN_LIMIT_WAIT_SECONDS)
    reset = response.headers.get("x-ratelimit-reset")
    if _is_secondary_limit(response) and reset is not None and reset.isdigit():
        return max(float(reset) - now, MIN_LIMIT_WAIT_SECONDS)
    return backoff_delay(attempt)


def _rate_snapshot(response: httpx.Response) -> RateSnapshot | None:
    headers = response.headers
    limit = headers.get("x-ratelimit-limit")
    remaining = headers.get("x-ratelimit-remaining")
    reset = headers.get("x-ratelimit-reset")
    if limit is None or remaining is None or reset is None:
        return None
    resource = headers.get("x-ratelimit-resource", "default")
    return RateSnapshot(
        resource=resource, limit=int(limit), remaining=int(remaining), reset_epoch=int(reset)
    )


class HttpClient:
    """One httpx.Client behind per-endpoint token buckets and a retry loop."""

    def __init__(
        self,
        *,
        user_agent: str,
        headers: Mapping[str, str],
        buckets: Mapping[str, TokenBucket],
        transport: httpx.BaseTransport | None,
        timing: Timing,
    ) -> None:
        """Bind default headers and buckets; a transport replays fixtures."""
        self._buckets: Final[Mapping[str, TokenBucket]] = buckets
        self._timing: Final[Timing] = timing
        self._headroom: dict[str, RateSnapshot] = {}
        base_headers = {"User-Agent": user_agent, **headers}
        self._client: Final[httpx.Client] = httpx.Client(
            headers=base_headers,
            transport=transport,
            timeout=REQUEST_TIMEOUT_SECONDS,
            follow_redirects=True,
        )

    def close(self) -> None:
        """Release the underlying connection pool."""
        self._client.close()

    def rate_headroom(self) -> dict[str, RateSnapshot]:
        """Latest rate-limit reading per API resource.

        Returns:
            Resource name to its most recent snapshot.
        """
        return dict(self._headroom)

    def _note_rate(self, response: httpx.Response) -> None:
        snapshot = _rate_snapshot(response)
        if snapshot is not None:
            self._headroom[snapshot.resource] = snapshot

    def _attempt(self, spec: _RequestSpec) -> httpx.Response | None:
        try:
            return self._client.request(
                spec.method, spec.url, params=spec.params, headers=spec.headers, json=spec.payload
            )
        except httpx.TransportError:
            return None

    def _request(self, spec: _RequestSpec, bucket: str) -> httpx.Response:
        response: httpx.Response | None = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            self._buckets[bucket].acquire()
            response = self._attempt(spec)
            if response is not None:
                self._note_rate(response)
                if not _is_retryable(response) or attempt == MAX_ATTEMPTS:
                    return response
                self._timing.sleep(_retry_delay(response, attempt, self._timing.clock()))
            elif attempt < MAX_ATTEMPTS:
                self._timing.sleep(backoff_delay(attempt))
        if response is None:
            raise HttpStatusError(0, spec.url)
        return response

    def get(  # noqa: PLR0913 - the conditional-request surface is one cohesive call
        self,
        url: str,
        *,
        bucket: str,
        params: Mapping[str, str] | None = None,
        accept: str | None = None,
        etag: str | None = None,
        allow: frozenset[int] = frozenset(),
    ) -> FetchedResponse:
        """GET with rate limiting, retries, and optional conditional request.

        Args:
            url: Absolute request URL.
            bucket: Token-bucket name governing this endpoint.
            params: Query parameters.
            accept: Accept header override.
            etag: Prior ETag; sent as If-None-Match (a 304 surfaces unretried).
            allow: Extra statuses to surface instead of raising (e.g. 404).

        Returns:
            The response; 2xx, 304, and allowed statuses surface (any other
            status raises HttpStatusError after retries).
        """
        headers: dict[str, str] = {}
        if accept is not None:
            headers["Accept"] = accept
        if etag is not None:
            headers["If-None-Match"] = etag
        spec = _RequestSpec(
            method="GET", url=url, params=params, headers=headers or None, payload=None
        )
        return self._surface(self._request(spec, bucket), url, allow)

    def post_json(
        self,
        url: str,
        payload: Mapping[str, object],
        *,
        bucket: str,
        params: Mapping[str, str] | None = None,
        allow: frozenset[int] = frozenset(),
    ) -> FetchedResponse:
        """POST a JSON payload with rate limiting and retries.

        Args:
            url: Absolute request URL.
            payload: The JSON body.
            bucket: Token-bucket name governing this endpoint.
            params: Query parameters.
            allow: Extra statuses to surface instead of raising.

        Returns:
            The response; 2xx and allowed statuses surface (any other status
            raises HttpStatusError after retries).
        """
        spec = _RequestSpec(method="POST", url=url, params=params, headers=None, payload=payload)
        return self._surface(self._request(spec, bucket), url, allow)

    def _surface(
        self, response: httpx.Response, url: str, allow: frozenset[int]
    ) -> FetchedResponse:
        ok = response.is_success or response.status_code == NOT_MODIFIED_STATUS
        if not ok and response.status_code not in allow:
            raise HttpStatusError(response.status_code, url)
        return FetchedResponse(
            status=response.status_code,
            body=response.content,
            etag=response.headers.get("ETag"),
            headers=dict(response.headers),
        )
