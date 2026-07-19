# Copyright (c) 2026 Venture Hunt. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Targeted hydration: --repos/--from-hacknation bypass star-based discovery."""

from datetime import UTC, date, datetime
from typing import Final

import httpx
import pytest

from contracts.models import Cursor
from scrapers.common.cli import HACKNATION_REPOS_MARKER, ScraperContext
from scrapers.common.http import HttpClient, TokenBucket
from scrapers.common.log import get_logger
from scrapers.common.settings import offline_scraper_settings
from scrapers.github.__main__ import (
    HacknationRepoSourceError,
    full_name,
    hacknation_repos,
    resolve_repos,
)
from scrapers.github.client_gql import GithubGraphql
from scrapers.github.client_rest import GithubRest
from scrapers.github.scraper import GithubDeps, GithubScraper, NullReadback
from tests.scrapers.conftest import FakeTime

FROZEN_NOW: Final[datetime] = datetime(2026, 7, 19, 12, 0, 0, tzinfo=UTC)


def test_full_name_parses_urls_and_bare_names() -> None:
    assert full_name("https://github.com/grasplab/grasp-anything") == "grasplab/grasp-anything"
    assert full_name("https://github.com/a/b.git") == "a/b"
    assert full_name("https://github.com/a/b/tree/main") == "a/b"
    assert full_name("github.com/a/b?tab=readme") == "a/b"
    assert full_name("grasplab/grasp-anything") == "grasplab/grasp-anything"
    assert full_name("not-a-repo") is None


def targeted_scraper(handler: httpx.MockTransport, repos: tuple[str, ...]) -> GithubScraper:
    time = FakeTime()
    http = HttpClient(
        user_agent="test-agent",
        headers={},
        buckets={
            "search": TokenBucket(1000.0, 10.0, timing=time.timing()),
            "core": TokenBucket(1000.0, 10.0, timing=time.timing()),
            "graphql": TokenBucket(1000.0, 10.0, timing=time.timing()),
        },
        transport=handler,
        timing=time.timing(),
    )
    log = get_logger("test")
    return GithubScraper(
        GithubDeps(
            rest=GithubRest(http),
            gql=GithubGraphql(http, log),
            readback=NullReadback(),
            since=date(2026, 6, 19),
            limit=0,
            clock=lambda: FROZEN_NOW,
            run_id="targeted-run",
            log=log,
            explicit_repos=repos,
        )
    )


def test_targeted_fetch_hydrates_the_named_repos_and_skips_missing() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        seen.append(path)
        if path == "/repos/grasplab/grasp-anything":
            return httpx.Response(
                200,
                json={
                    "node_id": "R_hn01",
                    "id": 9101,
                    "full_name": "grasplab/grasp-anything",
                    "stargazers_count": 42,
                },
            )
        if path == "/repos/gone/repo":
            return httpx.Response(404)
        if path == "/graphql":
            return httpx.Response(
                200,
                json={
                    "data": {"n0": {"databaseId": 9101, "nameWithOwner": "grasplab/grasp-anything"}}
                },
            )
        if path.endswith("/readme"):
            return httpx.Response(404)
        if path.endswith("/contributors"):
            return httpx.Response(200, json=[])
        return httpx.Response(500)

    scraper = targeted_scraper(
        httpx.MockTransport(handler),
        ("grasplab/grasp-anything", "gone/repo", "grasplab/grasp-anything"),
    )
    batches = list(scraper.fetch(Cursor(source="github", state={})))
    repos = [item for batch in batches for item in batch.items if item.get("kind") == "repo"]
    assert [item["full_name"] for item in repos] == ["grasplab/grasp-anything"]
    # Star-based discovery never runs in targeted mode.
    assert not any(path.startswith("/search") for path in seen)


class FakeRunner:
    """A warehouse stand-in answering the hacknation URL query."""

    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        """Store the canned rows."""
        self.rows: Final[list[tuple[object, ...]]] = rows
        self.statements: Final[list[str]] = []

    def execute(self, statement: str) -> list[tuple[object, ...]]:
        """Record and answer."""
        self.statements.append(statement)
        return self.rows


def test_hacknation_repos_reads_project_urls() -> None:
    runner = FakeRunner(
        [
            ("https://github.com/grasplab/grasp-anything",),
            ("https://github.com/other/tool.git",),
            ("not-a-url",),
        ]
    )
    names = hacknation_repos(runner, "dealflow_dev")
    assert names == ["grasplab/grasp-anything", "other/tool"]
    assert "bronze.hacknation_projects_raw" in runner.statements[0]
    assert "dealflow_dev." in runner.statements[0]


def test_from_hacknation_requires_a_warehouse() -> None:
    context = ScraperContext(
        settings=offline_scraper_settings(),
        transport=None,
        warehouse=None,
        limit=0,
        since=date(2026, 6, 19),
        catalog="dealflow_dev",
        repos=(HACKNATION_REPOS_MARKER,),
    )
    with pytest.raises(HacknationRepoSourceError, match="live warehouse"):
        resolve_repos(context)


def test_explicit_repo_urls_are_normalized_and_deduplicated() -> None:
    context = ScraperContext(
        settings=offline_scraper_settings(),
        transport=None,
        warehouse=None,
        limit=0,
        since=date(2026, 6, 19),
        catalog="dealflow_dev",
        repos=("https://github.com/a/b", "a/b", "https://github.com/c/d.git", "junk"),
    )
    assert resolve_repos(context) == ("a/b", "c/d")
