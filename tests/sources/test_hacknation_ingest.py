"""HN1: fixture-replay ingest into the two bronze tables via the NullSink."""

import json
from datetime import UTC, datetime
from typing import Final

import httpx

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
from sources.hacknation.replay import FIXTURE_DIR, fixture_transport

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
    assert report == IngestReport(people=6, projects=2, skipped_non_json=1, skipped_failed=0)
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


def test_persistent_upstream_failure_skips_the_project_without_losing_the_run() -> None:
    # The live endpoint 502s on some ids even after retries; the run must
    # still land every healthy project plus the whole people spine.
    people_body = json.loads((FIXTURE_DIR / "people.json").read_text(encoding="utf-8"))

    def handler(request: httpx.Request) -> httpx.Response:
        if "bff-public-people-v2" in str(request.url):
            return httpx.Response(200, json=people_body)
        return httpx.Response(502)

    timing = Timing(clock=lambda: 0.0, sleep=lambda _seconds: None)
    http = HttpClient(
        user_agent="dealflow-tests",
        headers={},
        buckets={BUCKET: TokenBucket(1.0, 100.0, timing=timing)},
        transport=httpx.MockTransport(handler),
        timing=timing,
    )
    sink = NullSink()
    report = run_ingest(
        IngestContext(
            client=HacknationClient(http),
            sink=sink,
            log=get_logger("hacknation-test"),
            clock=lambda: FROZEN_NOW,
            run_id=RUN_ID,
            limit=0,
        )
    )
    assert report.people == 6
    assert report.projects == 0
    assert report.skipped_failed == 3
    assert len(sink.rows[PEOPLE_TABLE]) == 6
