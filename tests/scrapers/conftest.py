# Copyright (c) 2026 Venture Hunt. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Shared fakes: deterministic time and a recording sink."""

from typing import Final

from contracts.models import SinkRow, UpsertResult
from scrapers.common.http import Timing


class FakeTime:
    """A clock that only advances when something sleeps."""

    def __init__(self) -> None:
        """Start at a fixed epoch."""
        self.now: float = 1_000.0
        self.sleeps: Final[list[float]] = []

    def clock(self) -> float:
        """Return the current fake time."""
        return self.now

    def sleep(self, seconds: float) -> None:
        """Record the sleep and advance the clock."""
        self.sleeps.append(seconds)
        self.now += seconds

    def timing(self) -> Timing:
        """Bundle this fake as an injectable Timing."""
        return Timing(clock=self.clock, sleep=self.sleep)


class RecordingSink:
    """A Sink that records every upsert call and reports rows inserted."""

    def __init__(self) -> None:
        """Start with no calls."""
        self.calls: Final[list[tuple[str, list[SinkRow], list[str], frozenset[str]]]] = []

    def upsert(
        self,
        table: str,
        rows: list[SinkRow],
        keys: list[str],
        *,
        variant_cols: frozenset[str] = frozenset(),
        hash_col: str = "content_hash",
    ) -> UpsertResult:
        """Record the call and count every row as inserted."""
        del hash_col
        self.calls.append((table, [dict(row) for row in rows], list(keys), variant_cols))
        return UpsertResult(
            table=table, inserted=len(rows), updated=0, skipped_unchanged=0, suppressed=0
        )
