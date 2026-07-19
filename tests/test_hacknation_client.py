# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""HacknationClient behavior, exercised through injected httpx.MockTransport handlers."""

from collections.abc import Callable
from typing import Final

import httpx
import pytest

from sources.hacknation.client import USER_AGENT, HacknationClient, NonJsonResponseError

_HTML_HEADERS: Final[dict[str, str]] = {"content-type": "text/html; charset=UTF-8"}


def _no_sleep(_seconds: float) -> None:
    """Stand-in for time.sleep so tests never wait."""


def _client(
    handler: Callable[[httpx.Request], httpx.Response],
    sleep: Callable[[float], None] = _no_sleep,
) -> HacknationClient:
    return HacknationClient(
        transport=httpx.MockTransport(handler), request_delay_s=0.0, sleep=sleep
    )


def _spa_fallback(_request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, headers=_HTML_HEADERS, content=b"<!doctype html><html></html>")


def test_people_parses_json_and_sends_user_agent() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"data": {"people": [], "contributionsByUserId": {}}})

    with _client(handler) as client:
        body = client.people(limit=7)
    assert body == {"data": {"people": [], "contributionsByUserId": {}}}
    assert requests[0].headers["User-Agent"] == USER_AGENT
    assert requests[0].url == httpx.URL(
        "https://projects.hack-nation.ai/.netlify/functions/bff-public-people-v2?limit=7"
    )


def test_project_parses_json_and_sends_user_agent() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"data": {"id": "p-1"}, "meta": {}})

    with _client(handler) as client:
        body = client.project("p-1")
    assert body == {"data": {"id": "p-1"}, "meta": {}}
    assert requests[0].headers["User-Agent"] == USER_AGENT
    assert requests[0].url == httpx.URL(
        "https://projects.hack-nation.ai/.netlify/functions/bff-projects-public-v2?id=p-1"
    )


def test_people_spa_fallback_raises_non_json_error() -> None:
    with _client(_spa_fallback) as client, pytest.raises(NonJsonResponseError, match="text/html"):
        client.people()


def test_project_spa_fallback_raises_non_json_error() -> None:
    with _client(_spa_fallback) as client, pytest.raises(NonJsonResponseError, match="text/html"):
        client.project("p-1")


def test_retry_after_429_then_succeeds() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(429, json={"error": "throttled"})
        return httpx.Response(200, json={"data": {"id": "p-1"}, "meta": {}})

    slept: list[float] = []
    with _client(handler, sleep=slept.append) as client:
        body = client.project("p-1")
    assert body == {"data": {"id": "p-1"}, "meta": {}}
    assert len(requests) == 2
    # First the request delay (0.0 injected), then the 2**0 backoff.
    assert slept == [0.0, 1.0]


def test_retry_after_5xx_and_no_delay_before_people() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) < 3:
            return httpx.Response(503, content=b"upstream sad")
        return httpx.Response(200, json={"data": {"people": []}})

    slept: list[float] = []
    with _client(handler, sleep=slept.append) as client:
        body = client.people()
    assert body == {"data": {"people": []}}
    assert len(requests) == 3
    # Backoffs only: people() is a single call and never sleeps a request delay.
    assert slept == [1.0, 2.0]


def test_retry_exhaustion_raises_last_http_error() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(503, content=b"still sad")

    with (
        _client(handler, sleep=_no_sleep) as client,
        pytest.raises(httpx.HTTPStatusError, match="503"),
    ):
        client.people()
    assert len(requests) == 3


def test_client_error_raises_immediately_without_retry() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(404, json={"error": "not found"})

    with _client(handler) as client, pytest.raises(httpx.HTTPStatusError, match="404"):
        client.project("missing")
    assert len(requests) == 1


def test_cookie_header_attached_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HACKNATION_COOKIE", "hn_session=s3cr3t")
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"data": {"people": []}})

    with _client(handler) as client:
        client.people()
    assert requests[0].headers["Cookie"] == "hn_session=s3cr3t"


def test_no_cookie_header_without_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HACKNATION_COOKIE", raising=False)
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"data": {"people": []}})

    with _client(handler) as client:
        client.people()
    assert "Cookie" not in requests[0].headers
