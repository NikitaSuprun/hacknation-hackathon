# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""End-to-end fixture replay for arXiv and OpenAlex, fully offline.

The CI proxy for P1/P2 acceptance: Atom pages flow through paging, cross-list
dedupe, PublicationRecord validation, and the runner; OpenAlex drains the
fixture pending queue with a batch hit, a single-lookup 404 miss, and the
match rate logged.
"""

from datetime import UTC, date, datetime
from typing import Final

from contracts.models import RunResult
from scrapers.common.base import RunnerDeps, execute_run
from scrapers.common.http import HttpClient, TokenBucket
from scrapers.common.jsonutil import as_mapping
from scrapers.common.log import get_logger
from scrapers.common.state import MemoryStateStore
from scrapers.papers.arxiv_client import ArxivClient, ArxivDeps, ArxivScraper
from scrapers.papers.openalex_client import (
    OpenAlexClient,
    OpenAlexDeps,
    OpenAlexScraper,
    StaticPendingWorks,
)
from scrapers.papers.replay import fixture_pending, fixture_routes
from tests.scrapers.conftest import FakeTime, RecordingSink

SINCE: Final[date] = date(2026, 6, 19)
FROZEN_NOW: Final[datetime] = datetime(2026, 7, 19, 12, 0, 0, tzinfo=UTC)


def replay_http() -> HttpClient:
    time = FakeTime()
    return HttpClient(
        user_agent="dealflow-scraper/0.1 (+mailto:test@example.invalid)",
        headers={},
        buckets={
            "arxiv": TokenBucket(1000.0, 10.0, timing=time.timing()),
            "openalex": TokenBucket(1000.0, 10.0, timing=time.timing()),
        },
        transport=fixture_routes(),
        timing=time.timing(),
    )


def run_arxiv() -> tuple[RecordingSink, RunResult]:
    scraper = ArxivScraper(
        ArxivDeps(
            client=ArxivClient(replay_http()),
            since=SINCE,
            limit=0,
            clock=lambda: FROZEN_NOW,
            run_id="fixture-run",
            log=get_logger("papers.arxiv"),
        )
    )
    sink = RecordingSink()
    deps = RunnerDeps(
        sink=sink, state=MemoryStateStore(), warehouse=None, log=get_logger("papers.arxiv")
    )
    return sink, execute_run(scraper, deps, SINCE)


def run_openalex() -> tuple[RecordingSink, RunResult]:
    log = get_logger("papers.openalex")
    scraper = OpenAlexScraper(
        OpenAlexDeps(
            client=OpenAlexClient(replay_http(), None, log),
            pending=StaticPendingWorks(fixture_pending()),
            since=SINCE,
            limit=0,
            clock=lambda: FROZEN_NOW,
            run_id="fixture-run",
            log=log,
        )
    )
    sink = RecordingSink()
    deps = RunnerDeps(sink=sink, state=MemoryStateStore(), warehouse=None, log=log)
    return sink, execute_run(scraper, deps, SINCE)


def rows_for(sink: RecordingSink, table: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for called_table, called_rows, _keys, _variants in sink.calls:
        if called_table == table:
            rows.extend(called_rows)
    return rows


def test_arxiv_replay_dedupes_cross_lists_and_rejects_malformed() -> None:
    sink, result = run_arxiv()
    papers = rows_for(sink, "bronze.arxiv_papers_raw")
    rejects = rows_for(sink, "bronze._rejects")
    ids = sorted(str(row["arxiv_id"]) for row in papers)
    # GraspFM appears in both category feeds; it must land exactly once.
    assert ids == ["2506.11111", "2507.22222", "2507.33333", "2507.44444"]
    assert result.items_upserted == 4
    assert result.rejects == 1
    assert rejects[0]["source"] == "papers.arxiv"


def test_arxiv_replay_extracts_code_links_and_versions() -> None:
    sink, _result = run_arxiv()
    by_id = {str(row["arxiv_id"]): row for row in rows_for(sink, "bronze.arxiv_papers_raw")}
    graspfm = by_id["2506.11111"]
    assert graspfm["latest_version"] == 2
    payload = as_mapping(graspfm["payload"])
    assert payload["code_links"] == ["https://github.com/grasplab/grasp-anything"]
    fastsim_payload = as_mapping(by_id["2507.22222"]["payload"])
    assert fastsim_payload["code_links"] == ["https://github.com/bergerlab/fastsim"]


def test_arxiv_replay_is_idempotent() -> None:
    sink_one, _one = run_arxiv()
    sink_two, _two = run_arxiv()
    assert rows_for(sink_one, "bronze.arxiv_papers_raw") == rows_for(
        sink_two, "bronze.arxiv_papers_raw"
    )


def test_openalex_replay_enriches_hits_and_logs_misses() -> None:
    sink, result = run_openalex()
    works = rows_for(sink, "bronze.openalex_works_raw")
    ids = sorted(str(row["openalex_id"]) for row in works)
    assert ids == ["W4400000001", "W4400000003"]
    assert result.items_upserted == 2
    assert result.rejects == 0
    by_id = {str(row["openalex_id"]): row for row in works}
    assert by_id["W4400000001"]["arxiv_id"] == "2506.11111"
    payload = as_mapping(by_id["W4400000001"]["payload"])
    assert payload["abstract"] == "We present GraspFM, a foundation model for grasping."
