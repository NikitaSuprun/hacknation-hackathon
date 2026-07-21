"""arXiv client behavior: query construction, pacing, empty-page retry."""

from datetime import date
from typing import Final

import httpx

from scrapers.common.http import HttpClient, TokenBucket
from scrapers.papers.arxiv_client import ArxivClient, slice_windows
from tests.scrapers.conftest import FakeTime

EMPTY_FEED: Final[str] = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<feed xmlns="http://www.w3.org/2005/Atom" '
    'xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">\n'
    "  <opensearch:totalResults>5</opensearch:totalResults>\n"
    "</feed>\n"
)
ONE_ENTRY_FEED: Final[str] = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<feed xmlns="http://www.w3.org/2005/Atom" '
    'xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">\n'
    "  <opensearch:totalResults>5</opensearch:totalResults>\n"
    "  <entry><id>http://arxiv.org/abs/2507.00001v1</id>"
    "<title>T</title><summary>S</summary></entry>\n"
    "</feed>\n"
)


def make_client(
    responses: list[str], seen: list[httpx.Request], rate: float = 1000.0
) -> ArxivClient:
    queue = iter(responses)
    time = FakeTime()

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=next(queue).encode())

    http = HttpClient(
        user_agent="dealflow-scraper/0.1 (+mailto:test@example.invalid)",
        headers={},
        buckets={"arxiv": TokenBucket(rate, 1.0, timing=time.timing())},
        transport=httpx.MockTransport(handler),
        timing=time.timing(),
    )
    return ArxivClient(http)


def test_query_string_is_golden() -> None:
    seen: list[httpx.Request] = []
    client = make_client([ONE_ENTRY_FEED], seen)
    client.query("cs.LG", date(2026, 6, 19), date(2026, 6, 21), 0)
    params = seen[0].url.params
    assert params["search_query"] == "cat:cs.LG AND submittedDate:[202606190000 TO 202606212359]"
    assert params["sortBy"] == "submittedDate"
    assert params["sortOrder"] == "ascending"
    assert params["start"] == "0"
    assert params["max_results"] == "200"


def test_offset_is_passed_through() -> None:
    seen: list[httpx.Request] = []
    client = make_client([ONE_ENTRY_FEED], seen)
    client.query("cs.LG", date(2026, 6, 19), date(2026, 6, 21), 200)
    assert seen[0].url.params["start"] == "200"


def test_empty_page_with_outstanding_results_retries_once() -> None:
    seen: list[httpx.Request] = []
    client = make_client([EMPTY_FEED, ONE_ENTRY_FEED], seen)
    entries, total = client.query("cs.LG", date(2026, 6, 19), date(2026, 6, 21), 0)
    assert len(seen) == 2
    assert total == 5
    assert len(entries) == 1


def test_arxiv_pacing_is_one_request_per_three_seconds() -> None:
    seen: list[httpx.Request] = []
    time = FakeTime()
    queue = iter([ONE_ENTRY_FEED, ONE_ENTRY_FEED])

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=next(queue).encode())

    http = HttpClient(
        user_agent="test",
        headers={},
        buckets={"arxiv": TokenBucket(1.0 / 3.0, 1.0, timing=time.timing())},
        transport=httpx.MockTransport(handler),
        timing=time.timing(),
    )
    client = ArxivClient(http)
    client.query("cs.LG", date(2026, 6, 19), date(2026, 6, 21), 0)
    client.query("cs.LG", date(2026, 6, 19), date(2026, 6, 21), 200)
    assert time.sleeps == [3.0]


def test_slice_windows_cover_the_range_without_overlap() -> None:
    slices = list(slice_windows(date(2026, 6, 19), date(2026, 6, 27)))
    assert slices == [
        (date(2026, 6, 19), date(2026, 6, 21)),
        (date(2026, 6, 22), date(2026, 6, 24)),
        (date(2026, 6, 25), date(2026, 6, 27)),
    ]
    assert list(slice_windows(date(2026, 6, 19), date(2026, 6, 19))) == [
        (date(2026, 6, 19), date(2026, 6, 19))
    ]
