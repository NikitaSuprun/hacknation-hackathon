# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""HN1: fixture-replay ingest into the two bronze tables via the NullSink."""

from datetime import UTC, datetime
from typing import Final

from scrapers.common.http import HttpClient, Timing, TokenBucket
from scrapers.common.log import get_logger
from scrapers.common.sink import NullSink
from sources.hacknation.client import BUCKET, HacknationClient
from sources.hacknation.ingest import (
    PEOPLE_TABLE,
    PROJECTS_TABLE,
    IngestContext,
    IngestReport,
    run_ingest,
)
from sources.hacknation.replay import fixture_transport

FROZEN_NOW: Final[datetime] = datetime(2026, 7, 15, 8, 0, 0, tzinfo=UTC)
RUN_ID: Final[str] = "test-run-hn"
PROVENANCE_COLUMNS: Final[tuple[str, ...]] = (
    "content_hash",
    "source_url",
    "scraped_at",
    "ingested_at",
    "scrape_run_id",
)


def _ingest(limit: int = 0) -> tuple[IngestReport, NullSink]:
    timing = Timing(clock=lambda: 0.0, sleep=lambda _seconds: None)
    http = HttpClient(
        user_agent="dealflow-tests",
        headers={},
        buckets={BUCKET: TokenBucket(1.0, 100.0, timing=timing)},
        transport=fixture_transport(),
        timing=timing,
    )
    sink = NullSink()
    context = IngestContext(
        client=HacknationClient(http),
        sink=sink,
        log=get_logger("hacknation-test"),
        clock=lambda: FROZEN_NOW,
        run_id=RUN_ID,
        limit=limit,
    )
    return run_ingest(context), sink


def test_full_replay_lands_people_and_projects_and_skips_the_spa_route() -> None:
    report, sink = _ingest()
    assert report == IngestReport(people=6, projects=2, skipped_non_json=1)
    people = sink.rows[PEOPLE_TABLE]
    projects = sink.rows[PROJECTS_TABLE]
    assert [row["user_id"] for row in people] == [
        "hn-lena-01",
        "hn-noah-01",
        "hn-mira-01",
        "hn-extra-01",
        "hn-extra-02",
        "hn-extra-03",
    ]
    assert [row["project_id"] for row in projects] == ["hnp-grasp-01", "hnp-voice-01"]


def test_rows_carry_the_provenance_quad_and_content_hash() -> None:
    _, sink = _ingest()
    for table in (PEOPLE_TABLE, PROJECTS_TABLE):
        for row in sink.rows[table]:
            for column in PROVENANCE_COLUMNS:
                assert row[column] is not None, f"{table}.{column}"
            assert row["scrape_run_id"] == RUN_ID
            assert row["scraped_at"] == FROZEN_NOW
            content_hash = row["content_hash"]
            assert isinstance(content_hash, str)
            assert len(content_hash) == 64


def test_limit_caps_the_project_detail_fetches() -> None:
    report, sink = _ingest(limit=1)
    assert report.projects == 1
    assert [row["project_id"] for row in sink.rows[PROJECTS_TABLE]] == ["hnp-grasp-01"]
