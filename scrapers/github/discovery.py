# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Repo discovery: top-starred fast path plus created-date bisection.

REST search caps at 1000 results per query. The fast path (5 pages sorted by
stars) already yields the top 500 of the window; when the window holds more
than 1000 repos, the window is bisected by created date until every slice
fits, and slices are paginated exhaustively. Everything dedupes on node_id.
"""

from collections.abc import Iterator
from datetime import date, timedelta
from typing import Final, Protocol

from structlog.typing import FilteringBoundLogger

from scrapers.common.jsonutil import get_int, get_str
from scrapers.github.models import RepoStub, SearchWindow

MAX_SEARCH_RESULTS: Final[int] = 1_000
FAST_PATH_PAGES: Final[int] = 5
PAGE_SIZE: Final[int] = 100
DEFAULT_LIMIT: Final[int] = 500


class SearchClient(Protocol):
    """The search surface discovery needs (GithubRest fits)."""

    def search_total(self, start: date, end: date) -> int:
        """Probe the result count for a created window."""
        ...

    def search_page(self, start: date, end: date, page: int) -> list[dict[str, object]]:
        """One page of the created-window search, most-starred first."""
        ...


def _stub(item: dict[str, object]) -> RepoStub | None:
    node_id = get_str(item, "node_id")
    repo_id = get_int(item, "id")
    full_name = get_str(item, "full_name")
    if node_id is None or repo_id is None or full_name is None:
        return None
    return RepoStub(
        node_id=node_id,
        repo_id=repo_id,
        full_name=full_name,
        stars=get_int(item, "stargazers_count") or 0,
    )


def _paginate(rest: SearchClient, start: date, end: date, pages: int) -> Iterator[RepoStub]:
    for page in range(1, pages + 1):
        items = rest.search_page(start, end, page)
        for item in items:
            stub = _stub(item)
            if stub is not None:
                yield stub
        if len(items) < PAGE_SIZE:
            return


def bisect_windows(
    rest: SearchClient, start: date, end: date, log: FilteringBoundLogger
) -> Iterator[SearchWindow]:
    """Split the created window until every slice is under the search cap.

    Args:
        rest: The search client.
        start: Window start (inclusive).
        end: Window end (inclusive).
        log: Run logger (warns on un-splittable hot days).

    Yields:
        Slices whose result counts fit under the cap (hot single days are
        yielded truncated, with a warning).
    """
    stack: list[tuple[date, date]] = [(start, end)]
    while stack:
        window_start, window_end = stack.pop()
        total = rest.search_total(window_start, window_end)
        splittable = window_start < window_end
        if total >= MAX_SEARCH_RESULTS and splittable:
            middle = window_start + (window_end - window_start) // 2
            stack.append((middle + timedelta(days=1), window_end))
            stack.append((window_start, middle))
            continue
        if total >= MAX_SEARCH_RESULTS:
            log.warning("search window truncated", start=window_start.isoformat(), total=total)
        yield SearchWindow(start=window_start, end=window_end, total=total)


def discover(
    rest: SearchClient, start: date, end: date, limit: int, log: FilteringBoundLogger
) -> list[RepoStub]:
    """Discover the window's top repos: fast path, bisection only when needed.

    Args:
        rest: The search client.
        start: Window start (inclusive).
        end: Window end (inclusive).
        limit: Result cap (0 means the default top 500).
        log: Run logger.

    Returns:
        Deduped stubs, most-starred first, capped at the limit.
    """
    stubs: dict[str, RepoStub] = {}
    for stub in _paginate(rest, start, end, FAST_PATH_PAGES):
        stubs.setdefault(stub.node_id, stub)
    effective_limit = limit or DEFAULT_LIMIT
    total = rest.search_total(start, end)
    if total > MAX_SEARCH_RESULTS and effective_limit > len(stubs):
        for window in bisect_windows(rest, start, end, log):
            pages = -(-min(window.total, MAX_SEARCH_RESULTS) // PAGE_SIZE)
            for stub in _paginate(rest, window.start, window.end, pages):
                stubs.setdefault(stub.node_id, stub)
    ranked = sorted(stubs.values(), key=lambda stub: (-stub.stars, stub.full_name))
    log.info("discovery complete", found=len(ranked), window_total=total)
    return ranked[:effective_limit]
