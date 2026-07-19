# Copyright (c) 2026 Venture Hunt. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""S2 layer: clean no-op without a key, batching and promotion with one."""

from datetime import UTC, date, datetime
from typing import Final

import httpx

from contracts.models import Cursor, Json
from scrapers.common.http import HttpClient, TokenBucket
from scrapers.common.jsonutil import as_mapping
from scrapers.common.log import get_logger
from scrapers.papers.models import PendingPaper
from scrapers.papers.normalize import s2_paper_to_row
from scrapers.papers.openalex_client import StaticPendingWorks
from scrapers.papers.s2_client import S2Deps, S2Scraper
from tests.scrapers.conftest import FakeTime

NOW: Final[datetime] = datetime(2026, 7, 19, 12, 0, 0, tzinfo=UTC)
SINCE: Final[date] = date(2026, 6, 19)


def make_scraper(api_key: str | None, seen: list[httpx.Request], pending_count: int) -> S2Scraper:
    time = FakeTime()

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json=[
                {"paperId": f"s2-{index}", "title": f"P{index}", "externalIds": {}}
                for index in range(3)
            ],
        )

    http = HttpClient(
        user_agent="test",
        headers={},
        buckets={"s2": TokenBucket(1000.0, 10.0, timing=time.timing())},
        transport=httpx.MockTransport(handler),
        timing=time.timing(),
    )
    pending = StaticPendingWorks(
        tuple(
            PendingPaper(arxiv_id=f"2507.{index:05d}", doi=None) for index in range(pending_count)
        )
    )
    return S2Scraper(
        S2Deps(
            http=http,
            api_key=api_key,
            pending=pending,
            since=SINCE,
            limit=pending_count,
            clock=lambda: NOW,
            run_id="run-0001",
            log=get_logger("test"),
        )
    )


def test_without_key_is_a_noop_with_zero_requests() -> None:
    seen: list[httpx.Request] = []
    scraper = make_scraper(None, seen, pending_count=10)
    batches = list(scraper.fetch(Cursor(source="papers.s2", state={})))
    assert batches == []
    assert seen == []


def test_with_key_batches_500_ids_per_post() -> None:
    seen: list[httpx.Request] = []
    scraper = make_scraper("s2-key", seen, pending_count=600)
    batches = list(scraper.fetch(Cursor(source="papers.s2", state={})))
    assert len(seen) == 2
    assert len(batches) == 2
    first_body = seen[0].read().decode()
    assert '"ARXIV:2507.00000"' in first_body
    assert seen[0].url.params["fields"] == "externalIds,citationCount,tldr,title"


def test_row_promotion_is_golden() -> None:
    paper: dict[str, Json] = {
        "paperId": "649def34f8be52c8b66281af98ae884c09aef38b",
        "title": "GraspFM",
        "citationCount": 44,
        "tldr": {"model": "tldr@v2.0.0", "text": "A foundation model."},
        "externalIds": {"ArXiv": "2506.11111", "DOI": "10.48550/arXiv.2506.11111"},
    }
    row = s2_paper_to_row(paper, "run-0001", NOW, NOW)
    assert row["s2_id"] == "649def34f8be52c8b66281af98ae884c09aef38b"
    assert row["arxiv_id"] == "2506.11111"
    assert row["doi"] == "10.48550/arXiv.2506.11111"
    payload = as_mapping(row["payload"])
    assert payload["tldr"] == "A foundation model."
