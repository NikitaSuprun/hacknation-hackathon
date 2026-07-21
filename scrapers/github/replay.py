"""Fixture replay for the GitHub scraper (the --fixtures transport).

Responders assemble wire-shaped responses from committed maps (search page,
GraphQL objects keyed by name/login, contributor lists, READMEs), parsing the
aliases out of each GraphQL request so replay exercises the real query
construction and response handling.
"""

import json
import re
from pathlib import Path
from typing import Final

import httpx

from contracts.models import Json
from scrapers.common.fixtures import FixtureRoute, build_mock_transport
from scrapers.common.jsonutil import as_mapping

FIXTURES_DIR: Final[Path] = Path(__file__).parent / "fixtures"
REPO_ALIAS_RE: Final[re.Pattern[str]] = re.compile(
    r'(n\d+): repository\(owner: "([^"]+)", name: "([^"]+)"\)'
)
USER_ALIAS_RE: Final[re.Pattern[str]] = re.compile(r'(n\d+): user\(login: "([^"]+)"\)')
RATE_LIMIT_STUB: Final[dict[str, Json]] = {
    "cost": 1,
    "remaining": 4990,
    "resetAt": "2026-07-19T13:00:00Z",
}


def _load(name: str) -> dict[str, Json]:
    return as_mapping(json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8")))


def _search(request: httpx.Request) -> httpx.Response:
    search = _load("search.json")
    if request.url.params.get("per_page") == "1":
        return httpx.Response(200, json={"total_count": search.get("total_count"), "items": []})
    if request.url.params.get("page", "1") == "1":
        return httpx.Response(200, json=search)
    return httpx.Response(200, json={"total_count": search.get("total_count"), "items": []})


def _full_name(request: httpx.Request, suffix: str) -> str:
    match = re.search(rf"/repos/([^/]+/[^/]+)/{suffix}", request.url.path)
    return match.group(1) if match else ""


def _readme(request: httpx.Request) -> httpx.Response:
    text = _load("readmes.json").get(_full_name(request, "readme"))
    if not isinstance(text, str):
        return httpx.Response(404)
    etag = f'W/"readme-{_full_name(request, "readme")}"'
    if request.headers.get("If-None-Match") == etag:
        return httpx.Response(304, headers={"ETag": etag})
    return httpx.Response(
        200, content=text.encode(), headers={"Content-Type": "text/plain", "ETag": etag}
    )


def _contributors(request: httpx.Request) -> httpx.Response:
    entries = _load("contributors.json").get(_full_name(request, "contributors"))
    if entries is None:
        return httpx.Response(404)
    etag = f'W/"contrib-{_full_name(request, "contributors")}"'
    if request.headers.get("If-None-Match") == etag:
        return httpx.Response(304, headers={"ETag": etag})
    return httpx.Response(200, json=entries, headers={"ETag": etag})


def _graphql_payload(query: str) -> tuple[dict[str, Json], list[dict[str, Json]]]:
    data: dict[str, Json] = {"rateLimit": dict(RATE_LIMIT_STUB)}
    errors: list[dict[str, Json]] = []
    if "query Hydrate" in query:
        repos = _load("repos.json")
        pairs = [(alias, f"{owner}/{name}") for alias, owner, name in REPO_ALIAS_RE.findall(query)]
        universe: dict[str, Json] = repos
    else:
        universe = _load("users.json")
        pairs = list(USER_ALIAS_RE.findall(query))
    for alias, key in pairs:
        found = universe.get(key)
        data[alias] = found
        if found is None:
            errors.append(
                {
                    "type": "NOT_FOUND",
                    "path": [alias],
                    "message": f"Could not resolve {key!r}",
                }
            )
    return data, errors


def _graphql(request: httpx.Request) -> httpx.Response:
    body = as_mapping(json.loads(request.content))
    query = body.get("query")
    data, errors = _graphql_payload(query if isinstance(query, str) else "")
    payload: dict[str, Json] = {"data": data}
    if errors:
        payload["errors"] = list[Json](errors)
    return httpx.Response(200, json=payload)


def fixture_routes() -> httpx.MockTransport:
    """The replay transport covering every endpoint the scraper hits.

    Returns:
        A MockTransport for HttpClient (unmatched requests answer 418).
    """
    return build_mock_transport(
        (
            FixtureRoute("GET", re.compile(r"/search/repositories"), _search),
            FixtureRoute("GET", re.compile(r"/repos/[^/]+/[^/]+/readme"), _readme),
            FixtureRoute("GET", re.compile(r"/repos/[^/]+/[^/]+/contributors"), _contributors),
            FixtureRoute("POST", re.compile(r"/graphql"), _graphql),
        )
    )
