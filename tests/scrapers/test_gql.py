# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""GraphQL batching: query construction and the per-alias error policy."""

import json
from typing import Final

import httpx

from scrapers.common.http import HttpClient, TokenBucket
from scrapers.common.jsonutil import as_mapping
from scrapers.common.log import get_logger
from scrapers.github.client_gql import GithubGraphql, GqlFailure, repo_query, user_query
from scrapers.github.models import RepoStub
from tests.scrapers.conftest import FakeTime

STUBS: Final[list[RepoStub]] = [
    RepoStub(node_id="R_1", repo_id=1, full_name="octo/alpha", stars=10),
    RepoStub(node_id="R_2", repo_id=2, full_name="octo/beta", stars=9),
]


def test_repo_query_aliases_escaping_and_since() -> None:
    query = repo_query(["octo/alpha", 'we"ird/repo'], "2026-07-18T00:00:00Z")
    assert 'n0: repository(owner: "octo", name: "alpha")' in query
    assert 'n1: repository(owner: "we\\"ird", name: "repo")' in query
    assert 'history(first: 100, since: "2026-07-18T00:00:00Z")' in query
    assert "rateLimit { cost remaining resetAt }" in query
    assert query.startswith("query Hydrate {")


def test_repo_query_backfill_has_no_since() -> None:
    assert "since:" not in repo_query(["octo/alpha"], None)


def test_user_query_shape() -> None:
    query = user_query(["dev01", "dev02"])
    assert 'n0: user(login: "dev01") { ...UserFields }' in query
    assert 'n1: user(login: "dev02") { ...UserFields }' in query
    assert "socialAccounts(first: 10)" in query


def gql_client(responses: list[dict[str, object]], time: FakeTime) -> GithubGraphql:
    queue = iter(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, json=next(queue))

    http = HttpClient(
        user_agent="test-agent",
        headers={},
        buckets={"graphql": TokenBucket(100.0, 5.0, timing=time.timing())},
        transport=httpx.MockTransport(handler),
        timing=time.timing(),
    )
    return GithubGraphql(http, get_logger("test"))


def test_not_found_alias_is_dropped_without_retry() -> None:
    response: dict[str, object] = {
        "data": {"n0": {"databaseId": 1}, "n1": None},
        "errors": [{"type": "NOT_FOUND", "path": ["n1"], "message": "gone"}],
    }
    gql = gql_client([response], FakeTime())
    results, failures = gql.hydrate_repos(STUBS, None)
    assert set(results) == {"octo/alpha"}
    assert failures == []


def test_transient_alias_error_retried_individually_then_recovered() -> None:
    first: dict[str, object] = {
        "data": {"n0": {"databaseId": 1}, "n1": None},
        "errors": [{"type": "INTERNAL", "path": ["n1"], "message": "boom"}],
    }
    retry: dict[str, object] = {"data": {"n0": {"databaseId": 2}}}
    gql = gql_client([first, retry], FakeTime())
    results, failures = gql.hydrate_repos(STUBS, None)
    assert results["octo/beta"] == {"databaseId": 2}
    assert failures == []


def test_persistent_alias_error_becomes_failure() -> None:
    first: dict[str, object] = {
        "data": {"n0": {"databaseId": 1}, "n1": None},
        "errors": [{"type": "INTERNAL", "path": ["n1"], "message": "boom"}],
    }
    retry: dict[str, object] = {
        "data": {"n0": None},
        "errors": [{"type": "INTERNAL", "path": ["n0"], "message": "still boom"}],
    }
    gql = gql_client([first, retry], FakeTime())
    results, failures = gql.hydrate_repos(STUBS, None)
    assert set(results) == {"octo/alpha"}
    assert failures == [GqlFailure(key="octo/beta", message="still boom")]


def test_profiles_parse_by_login() -> None:
    response: dict[str, object] = {
        "data": {
            "n0": {"databaseId": 101, "login": "dev01"},
            "n1": {"databaseId": 102, "login": "dev02"},
        }
    }
    gql = gql_client([response], FakeTime())
    results, failures = gql.user_profiles(["dev01", "dev02"])
    assert results["dev02"] == {"databaseId": 102, "login": "dev02"}
    assert failures == []


def test_request_body_is_the_query_document() -> None:
    seen: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(as_mapping(json.loads(request.content)))
        return httpx.Response(200, json={"data": {"n0": {"databaseId": 1}}})

    time = FakeTime()
    http = HttpClient(
        user_agent="test-agent",
        headers={},
        buckets={"graphql": TokenBucket(100.0, 5.0, timing=time.timing())},
        transport=httpx.MockTransport(handler),
        timing=time.timing(),
    )
    GithubGraphql(http, get_logger("test")).user_profiles(["dev01"])
    query = seen[0]["query"]
    assert isinstance(query, str)
    assert query.startswith("query Profiles {")
