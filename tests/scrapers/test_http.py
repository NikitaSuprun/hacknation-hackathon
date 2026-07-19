# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""HTTP layer behavior: bucket timing, retries, Retry-After, ETags, headroom."""

import httpx
import pytest

from scrapers.common.http import HttpClient, HttpStatusError, TokenBucket
from tests.scrapers.conftest import FakeTime


def make_client(
    handler: httpx.MockTransport, time: FakeTime, rate: float = 100.0
) -> HttpClient:
    return HttpClient(
        user_agent="dealflow-scraper/0.1 (+mailto:test@example.invalid)",
        headers={"Authorization": "Bearer test-token"},
        buckets={"main": TokenBucket(rate, 1.0, timing=time.timing())},
        transport=handler,
        timing=time.timing(),
    )


def test_token_bucket_sleeps_when_drained() -> None:
    time = FakeTime()
    bucket = TokenBucket(0.5, 1.0, timing=time.timing())
    bucket.acquire()
    assert time.sleeps == []
    bucket.acquire()
    assert time.sleeps == [2.0]


def test_retry_then_success_backs_off_exponentially() -> None:
    time = FakeTime()
    statuses = iter([500, 502, 200])

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(next(statuses))

    client = make_client(httpx.MockTransport(handler), time)
    response = client.get("https://api.test/x", bucket="main")
    assert response.status == 200
    assert time.sleeps == [1.0, 2.0]


def test_retry_after_header_wins_over_backoff() -> None:
    time = FakeTime()
    statuses = iter([429, 200])

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        status = next(statuses)
        headers = {"Retry-After": "7"} if status == 429 else {}
        return httpx.Response(status, headers=headers)

    client = make_client(httpx.MockTransport(handler), time)
    assert client.get("https://api.test/x", bucket="main").status == 200
    assert time.sleeps == [7.0]


def test_secondary_limit_sleeps_until_reset() -> None:
    time = FakeTime()
    statuses = iter([403, 200])

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        status = next(statuses)
        headers = (
            {"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1030"} if status == 403 else {}
        )
        return httpx.Response(status, headers=headers)

    client = make_client(httpx.MockTransport(handler), time)
    assert client.get("https://api.test/x", bucket="main").status == 200
    assert time.sleeps == [30.0]


def test_plain_403_is_not_retried() -> None:
    time = FakeTime()
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(403)

    client = make_client(httpx.MockTransport(handler), time)
    with pytest.raises(HttpStatusError):
        client.get("https://api.test/x", bucket="main")
    assert len(calls) == 1


def test_etag_sent_and_304_surfaces_unretried() -> None:
    time = FakeTime()
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(304)

    client = make_client(httpx.MockTransport(handler), time)
    response = client.get("https://api.test/x", bucket="main", etag='W/"abc"')
    assert response.status == 304
    assert len(calls) == 1
    assert calls[0].headers["If-None-Match"] == 'W/"abc"'


def test_user_agent_and_auth_headers_sent() -> None:
    time = FakeTime()
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={})

    client = make_client(httpx.MockTransport(handler), time)
    client.get("https://api.test/x", bucket="main", accept="application/vnd.github.raw+json")
    assert seen[0].headers["User-Agent"] == "dealflow-scraper/0.1 (+mailto:test@example.invalid)"
    assert seen[0].headers["Authorization"] == "Bearer test-token"
    assert seen[0].headers["Accept"] == "application/vnd.github.raw+json"


def test_allowed_status_surfaces_instead_of_raising() -> None:
    time = FakeTime()

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(404)

    client = make_client(httpx.MockTransport(handler), time)
    response = client.get("https://api.test/missing", bucket="main", allow=frozenset({404}))
    assert response.status == 404


def test_rate_headroom_parsed_from_headers() -> None:
    time = FakeTime()

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            200,
            headers={
                "x-ratelimit-limit": "5000",
                "x-ratelimit-remaining": "4321",
                "x-ratelimit-reset": "1700000000",
                "x-ratelimit-resource": "core",
            },
        )

    client = make_client(httpx.MockTransport(handler), time)
    client.get("https://api.test/x", bucket="main")
    headroom = client.rate_headroom()
    assert headroom["core"].limit == 5000
    assert headroom["core"].remaining == 4321
