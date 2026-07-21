"""Fixture replay for the papers scrapers (the --fixtures transport).

One transport serves all papers sources: arXiv Atom pages are routed by the
category inside search_query (categories without a fixture answer an empty
feed), OpenAlex batch lookups answer the works file, single-work fallbacks
404 (exercising the miss path), and S2 batch POSTs answer the batch file.
"""

import json
import re
from pathlib import Path
from typing import Final

import httpx

from scrapers.common.fixtures import FixtureRoute, build_mock_transport
from scrapers.common.jsonutil import as_list, as_mapping, get_str
from scrapers.papers.models import PendingPaper

FIXTURES_DIR: Final[Path] = Path(__file__).parent / "fixtures"
CATEGORY_RE: Final[re.Pattern[str]] = re.compile(r"cat:([\w.\-]+)")
CATEGORY_FILES: Final[dict[str, str]] = {
    "cs.RO": "arxiv_cs_ro.atom.xml",
    "cs.LG": "arxiv_cs_lg.atom.xml",
}
EMPTY_FEED: Final[str] = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<feed xmlns="http://www.w3.org/2005/Atom" '
    'xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">\n'
    "  <opensearch:totalResults>0</opensearch:totalResults>\n"
    "</feed>\n"
)


def fixture_pending() -> tuple[PendingPaper, ...]:
    """The pending queue used by openalex/s2 fixture replay.

    Returns:
        Pending papers from the committed pending.json.
    """
    raw = json.loads((FIXTURES_DIR / "pending.json").read_text(encoding="utf-8"))
    return tuple(
        PendingPaper(
            arxiv_id=get_str(as_mapping(item), "arxiv_id") or "",
            doi=get_str(as_mapping(item), "doi"),
        )
        for item in as_list(raw)
    )


def _arxiv(request: httpx.Request) -> httpx.Response:
    params = request.url.params
    match = CATEGORY_RE.search(params.get("search_query", ""))
    category = match.group(1) if match else ""
    file_name = CATEGORY_FILES.get(category)
    if file_name is None or params.get("start", "0") != "0":
        return httpx.Response(200, content=EMPTY_FEED.encode(), headers=_ATOM_HEADERS)
    return httpx.Response(
        200, content=(FIXTURES_DIR / file_name).read_bytes(), headers=_ATOM_HEADERS
    )


_ATOM_HEADERS: Final[dict[str, str]] = {"Content-Type": "application/atom+xml"}


def _openalex_batch(request: httpx.Request) -> httpx.Response:
    del request
    return httpx.Response(
        200,
        content=(FIXTURES_DIR / "openalex_works.json").read_bytes(),
        headers={"Content-Type": "application/json", "x-ratelimit-remaining": "9950"},
    )


def _openalex_single(request: httpx.Request) -> httpx.Response:
    del request
    return httpx.Response(404)


def _s2_batch(request: httpx.Request) -> httpx.Response:
    del request
    return httpx.Response(200, content=(FIXTURES_DIR / "s2_batch.json").read_bytes())


def fixture_routes() -> httpx.MockTransport:
    """The replay transport covering every papers endpoint.

    Returns:
        A MockTransport for HttpClient (unmatched requests answer 418).
    """
    return build_mock_transport(
        (
            FixtureRoute("GET", re.compile(r"export\.arxiv\.org/api/query"), _arxiv),
            FixtureRoute(
                "GET", re.compile(r"api\.openalex\.org/works/https://doi\.org/"), _openalex_single
            ),
            FixtureRoute("GET", re.compile(r"api\.openalex\.org/works"), _openalex_batch),
            FixtureRoute(
                "POST", re.compile(r"api\.semanticscholar\.org/graph/v1/paper/batch"), _s2_batch
            ),
        )
    )
