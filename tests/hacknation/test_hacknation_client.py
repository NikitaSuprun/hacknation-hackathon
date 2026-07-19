# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""HacknationClient behavior on the shared HttpClient, over httpx.MockTransport."""

from collections.abc import Callable
from typing import Final

import httpx
import pytest

from scrapers.common.http import HttpClient, HttpStatusError, TokenBucket
from scrapers.hacknation.client import (
    BUCKET,
    HacknationClient,
    NonJsonResponseError,
    cookie_headers,
)
from tests.scrapers.conftest import FakeTime

_HTML_HEADERS: Final[dict[str, str]] = {"content-type": "text/html; charset=UTF-8"}
_USER_AGENT: Final[str] = "dealflow-scraper/0.1 (+mailto:test@example.invalid)"


def _client(
    handler: Callable[[httpx.Request], httpx.Response],
    headers: dict[str, str] | None = None,
) -> tuple[HacknationClient, FakeTime]:
    time = FakeTime()
    http = HttpClient(
        user_agent=_USER_AGENT,
        headers=headers or {},
        buckets={BUCKET: TokenBucket(1000.0, 10.0, timing=time.timing())},
        transport=httpx.MockTransport(handler),
        timing=time.timing(),
    )
    return HacknationClient(http), time


def _spa_fallback(_request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, headers=_HTML_HEADERS, content=b"<!doctype html><html></html>")


def test_people_parses_json_and_sends_user_agent() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"data": {"people": [], "contributionsByUserId": {}}})

    client, _time = _client(handler)
    body = client.people(limit=7)
    assert body == {"data": {"people": [], "contributionsByUserId": {}}}
    assert requests[0].headers["User-Agent"] == _USER_AGENT
    assert requests[0].headers["Accept"] == "application/json"
    assert requests[0].url == httpx.URL(
        "https://projects.hack-nation.ai/.netlify/functions/bff-public-people-v2?limit=7"
    )


def test_project_parses_json_and_builds_the_id_url() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"data": {"id": "p-1"}, "meta": {}})

    client, _time = _client(handler)
    body = client.project("p-1")
    assert body == {"data": {"id": "p-1"}, "meta": {}}
    assert requests[0].url == httpx.URL(
        "https://projects.hack-nation.ai/.netlify/functions/bff-projects-public-v2?id=p-1"
    )


def test_people_spa_fallback_raises_non_json_error() -> None:
    client, _time = _client(_spa_fallback)
    with pytest.raises(NonJsonResponseError, match="text/html"):
        client.people()


def test_project_spa_fallback_raises_non_json_error() -> None:
    client, _time = _client(_spa_fallback)
    with pytest.raises(NonJsonResponseError, match="text/html"):
        client.project("p-1")


def test_json_content_type_with_charset_is_accepted() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "application/json; charset=utf-8"},
            content=b'{"data": {"people": []}}',
        )

    client, _time = _client(handler)
    assert client.people() == {"data": {"people": []}}


def test_retry_on_503_then_succeeds() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(503, content=b"upstream sad")
        return httpx.Response(200, json={"data": {"people": []}})

    client, time = _client(handler)
    assert client.people() == {"data": {"people": []}}
    assert len(requests) == 2
    # The shared retry loop slept one backoff between the attempts.
    assert time.sleeps == [1.0]


def test_client_error_raises_immediately_without_retry() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(404, json={"error": "not found"})

    client, _time = _client(handler)
    with pytest.raises(HttpStatusError, match="404"):
        client.project("missing")
    assert len(requests) == 1


def test_cookie_header_travels_when_composed_in() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"data": {"people": []}})

    client, _time = _client(handler, headers={"Cookie": "hn_session=s3cr3t"})
    client.people()
    assert requests[0].headers["Cookie"] == "hn_session=s3cr3t"


def test_cookie_headers_read_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HACKNATION_COOKIE", "hn_session=s3cr3t")
    assert cookie_headers() == {"Cookie": "hn_session=s3cr3t"}


def test_cookie_headers_empty_without_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HACKNATION_COOKIE", raising=False)
    assert cookie_headers() == {}
