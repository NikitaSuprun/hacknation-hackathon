# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Discovery: fast path, 1000-cap bisection, node_id dedupe, limit cap."""

from datetime import date
from typing import Final

from scrapers.common.log import get_logger
from scrapers.github.discovery import bisect_windows, discover
from scrapers.github.models import SearchWindow

D1: Final[date] = date(2026, 7, 1)
D2: Final[date] = date(2026, 7, 2)
D3: Final[date] = date(2026, 7, 3)
D4: Final[date] = date(2026, 7, 4)


def item(node_id: str, repo_id: int, stars: int) -> dict[str, object]:
    return {
        "node_id": node_id,
        "id": repo_id,
        "full_name": f"o/{node_id}",
        "stargazers_count": stars,
    }


class FakeSearch:
    """Scripted totals and pages per (start, end) window."""

    def __init__(
        self,
        totals: dict[tuple[date, date], int],
        pages: dict[tuple[date, date], list[dict[str, object]]],
    ) -> None:
        """Store the scripted responses."""
        self.totals: Final[dict[tuple[date, date], int]] = totals
        self.pages: Final[dict[tuple[date, date], list[dict[str, object]]]] = pages
        self.total_calls: Final[list[tuple[date, date]]] = []

    def search_total(self, start: date, end: date) -> int:
        """Return the scripted total."""
        self.total_calls.append((start, end))
        return self.totals[(start, end)]

    def search_page(self, start: date, end: date, page: int) -> list[dict[str, object]]:
        """Return the scripted single page (page 1 only)."""
        if page > 1:
            return []
        return self.pages.get((start, end), [])


def test_bisection_splits_until_under_cap() -> None:
    totals = {
        (D1, D4): 2500,
        (D1, D2): 1200,
        (D3, D4): 1300,
        (D1, D1): 600,
        (D2, D2): 600,
        (D3, D3): 700,
        (D4, D4): 600,
    }
    rest = FakeSearch(totals, {})
    windows = list(bisect_windows(rest, D1, D4, get_logger("test")))
    assert windows == [
        SearchWindow(start=D1, end=D1, total=600),
        SearchWindow(start=D2, end=D2, total=600),
        SearchWindow(start=D3, end=D3, total=700),
        SearchWindow(start=D4, end=D4, total=600),
    ]


def test_hot_single_day_yields_truncated_window() -> None:
    rest = FakeSearch({(D1, D1): 1500}, {})
    windows = list(bisect_windows(rest, D1, D1, get_logger("test")))
    assert windows == [SearchWindow(start=D1, end=D1, total=1500)]


def test_discover_dedupes_across_fast_path_and_slices() -> None:
    shared = item("R_dup", 1, 300)
    totals = {(D1, D2): 1100, (D1, D1): 500, (D2, D2): 600}
    pages = {
        (D1, D2): [shared, item("R_top", 2, 900)],
        (D1, D1): [shared, item("R_a", 3, 100)],
        (D2, D2): [item("R_b", 4, 50)],
    }
    rest = FakeSearch(totals, pages)
    stubs = discover(rest, D1, D2, 0, get_logger("test"))
    assert [stub.node_id for stub in stubs] == ["R_top", "R_dup", "R_a", "R_b"]


def test_discover_respects_limit_and_skips_bisection_under_cap() -> None:
    totals = {(D1, D2): 900}
    pages = {(D1, D2): [item(f"R_{i}", i, 1000 - i) for i in range(1, 8)]}
    rest = FakeSearch(totals, pages)
    stubs = discover(rest, D1, D2, 3, get_logger("test"))
    assert [stub.node_id for stub in stubs] == ["R_1", "R_2", "R_3"]
    assert rest.total_calls == [(D1, D2)]


def test_discover_drops_malformed_search_items() -> None:
    totals = {(D1, D2): 2}
    malformed: dict[str, object] = {"node_id": "R_bad", "id": None}
    pages = {(D1, D2): [item("R_ok", 1, 10), malformed]}
    rest = FakeSearch(totals, pages)
    stubs = discover(rest, D1, D2, 0, get_logger("test"))
    assert [stub.node_id for stub in stubs] == ["R_ok"]
