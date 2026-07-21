"""End-to-end fixture replay: the whole WS-G pipeline over MockTransport, offline.

The three-persona fixture set flows through the people sweep, both project
fetches, the CV fetch+parse (LLM extraction answered by a fake warehouse),
the PSR merge, and both silver loads — zero credentials, zero network.
"""

from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from typing import Final, cast

import pytest

from contracts.models import SinkRow
from scrapers.common.base import RunnerDeps
from scrapers.common.http import HttpClient, TokenBucket
from scrapers.common.log import get_logger
from scrapers.common.state import MemoryStateStore
from scrapers.hacknation.client import BUCKET, HacknationClient
from scrapers.hacknation.cv import CV_BUCKET
from scrapers.hacknation.pipeline import PipelineDeps, PipelineSummary, run_pipeline
from scrapers.hacknation.replay import fixture_routes
from tests.scrapers.conftest import FakeTime, RecordingSink
from tools import ids
from tools.warehouse import Warehouse

SINCE: Final[date] = date(2026, 6, 19)
FROZEN_NOW: Final[datetime] = datetime(2026, 7, 19, 12, 0, 0, tzinfo=UTC)
LENA_ID: Final[str] = ids.psr_id("hacknation", "hn-lena-0001")
WEI_ID: Final[str] = ids.psr_id("hacknation", "hn-wei-0002")
SELIN_ID: Final[str] = ids.psr_id("hacknation", "hn-selin-0003")
SELIN_CV_URL: Final[str] = "https://cdn.hack-nation.ai/cv/hn-selin-0003.pdf"
KTH: Final[str] = "KTH Royal Institute of Technology"
PSR_TABLE: Final[str] = "silver.person_source_record"
PROJECT_TABLE: Final[str] = "silver.project"
CVS_TABLE: Final[str] = "bronze.hacknation_cvs_raw"

# What the fake ai_query answers for Selin's CV text.
EDUCATION_CELL: Final[str] = (
    '{"education": [{"institution": "KTH Royal Institute of Technology", "degree": "MSc", '
    '"field": "Autonomous Systems", "start_year": 2024, "end_year": 2026}], '
    '"experience": [], "skills": ["Python", "FastAPI"]}'
)


class _FakeCursor:
    _cell: str

    def __init__(self, cell: str) -> None:
        self._cell = cell

    def execute(self, operation: str, parameters: dict[str, str]) -> object:
        del operation, parameters
        return self

    def fetchall(self) -> list[tuple[object, ...]]:
        return [(self._cell,)]

    def close(self) -> None:
        return


class _FakeWarehouse:
    _cell: str

    def __init__(self, cell: str) -> None:
        self._cell = cell

    @contextmanager
    def cursor(self) -> Generator[_FakeCursor]:
        yield _FakeCursor(self._cell)


def _replay_http() -> HttpClient:
    time = FakeTime()
    return HttpClient(
        user_agent="dealflow-scraper/0.1 (+mailto:test@example.invalid)",
        headers={},
        buckets={
            BUCKET: TokenBucket(1000.0, 10.0, timing=time.timing()),
            CV_BUCKET: TokenBucket(1000.0, 10.0, timing=time.timing()),
        },
        transport=fixture_routes(),
        timing=time.timing(),
    )


def run_once(*, fetch_cvs: bool = True) -> tuple[PipelineSummary, RecordingSink, MemoryStateStore]:
    http = _replay_http()
    sink = RecordingSink()
    state = MemoryStateStore()
    log = get_logger("hacknation")
    warehouse = cast("Warehouse", cast("object", _FakeWarehouse(EDUCATION_CELL)))
    summary = run_pipeline(
        PipelineDeps(
            client=HacknationClient(http),
            http=http,
            runner=RunnerDeps(sink=sink, state=state, warehouse=warehouse, log=log),
            since=SINCE,
            limit=0,
            clock=lambda: FROZEN_NOW,
            run_id="fixture-run",
            log=log,
            catalog="dealflow_dev",
            fetch_cvs=fetch_cvs,
            workspace=None,
        )
    )
    return summary, sink, state


def rows_for(sink: RecordingSink, table: str) -> list[SinkRow]:
    rows: list[SinkRow] = []
    for called_table, called_rows, _keys, _variants in sink.calls:
        if called_table == table:
            rows.extend(called_rows)
    return rows


def psr_by_id(sink: RecordingSink) -> dict[str, SinkRow]:
    return {str(row["source_record_id"]): row for row in rows_for(sink, PSR_TABLE)}


def test_replay_produces_expected_counts() -> None:
    summary, sink, _state = run_once()
    assert summary == PipelineSummary(
        people=3, projects=2, rejects=0, cvs=1, psr=3, silver_projects=2
    )
    assert len(rows_for(sink, "bronze.hacknation_people_raw")) == 3
    assert len(rows_for(sink, "bronze.hacknation_projects_raw")) == 2
    assert len(rows_for(sink, CVS_TABLE)) == 1
    assert rows_for(sink, "bronze._rejects") == []


def test_replay_merges_one_psr_per_person() -> None:
    _summary, sink, _state = run_once()
    merged = psr_by_id(sink)
    assert sorted(merged) == sorted([LENA_ID, WEI_ID, SELIN_ID])

    lena = merged[LENA_ID]
    assert lena["full_name"] == "Léna Fischer"
    # The project author fragment fills what the people list never carries.
    assert lena["emails"] == ["lena.fischer@ethz.ch"]
    assert lena["email_domain"] == "ethz.ch"
    assert lena["linkedin_url"] == "linkedin.com/in/lena-fischer-robotics"
    assert lena["bio"] == "Building grasp foundation models for anything"
    assert lena["keywords"] == ["Robotics", "Python", "ROS2", "PyTorch"]
    assert lena["location_raw"] == "Zürich, Switzerland"
    assert lena["cv_url"] is None

    wei = merged[WEI_ID]
    assert wei["emails"] == []
    assert wei["keywords"] == ["Robot Learning", "Python", "ROS2", "PyTorch"]
    assert wei["avatar_url"] is None


def test_replay_folds_cv_education_into_selin() -> None:
    _summary, sink, _state = run_once()
    selin = psr_by_id(sink)[SELIN_ID]
    assert selin["cv_url"] == SELIN_CV_URL
    assert selin["emails"] == ["selin.aydin@careloop.se"]
    assert selin["linkedin_url"] == "linkedin.com/in/selin-aydin-kth"
    assert selin["keywords"] == ["Autonomous Systems", "Python", "FastAPI", "React", KTH]


def test_replay_upserts_with_registry_keys() -> None:
    _summary, sink, _state = run_once()
    keys_by_table = {table: keys for table, _rows, keys, _variants in sink.calls}
    assert keys_by_table[PSR_TABLE] == ["source_record_id"]
    assert keys_by_table[PROJECT_TABLE] == ["project_id"]
    assert keys_by_table[CVS_TABLE] == ["user_id"]
    variants_by_table = {table: variants for table, _rows, _keys, variants in sink.calls}
    assert variants_by_table[CVS_TABLE] == frozenset({"payload"})
    assert variants_by_table[PROJECT_TABLE] == frozenset({"structured"})


def test_replay_loads_silver_projects() -> None:
    _summary, sink, _state = run_once()
    by_id = {str(row["project_id"]): row for row in rows_for(sink, PROJECT_TABLE)}
    graspos = by_id[ids.hacknation_project_id("5f1e6d3a-9c2b-4e51-8a7d-000000000001")]
    careloop = by_id[ids.hacknation_project_id("5f1e6d3a-9c2b-4e51-8a7d-000000000002")]
    assert graspos["name"] == "GraspOS Studio"
    assert graspos["github_url"] == "github.com/grasplab/grasp-anything"
    assert graspos["is_winner"] is True
    assert graspos["contributor_count"] == 2
    assert careloop["github_url"] is None
    assert careloop["is_winner"] is False
    assert careloop["event_title"] == "HackNation Global AI Hackathon 2026"


def test_cv_bronze_row_carries_the_extraction(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HACKNATION_CV_ENDPOINT", raising=False)
    _summary, sink, _state = run_once()
    row = rows_for(sink, CVS_TABLE)[0]
    assert row["user_id"] == "hn-selin-0003"
    assert row["source_url"] == SELIN_CV_URL
    payload = row["payload"]
    assert isinstance(payload, dict)
    assert payload["volume_path"] == "/Volumes/dealflow_dev/ops/cv/hacknation/hn-selin-0003.pdf"
    assert payload["model"] == "databricks-claude-sonnet-4-6"
    extracted = payload["extracted"]
    assert isinstance(extracted, dict)
    education = extracted["education"]
    assert isinstance(education, list)
    first = education[0]
    assert isinstance(first, dict)
    assert first["institution"] == KTH


def test_no_cvs_run_skips_cv_rows_and_keywords() -> None:
    summary, sink, _state = run_once(fetch_cvs=False)
    assert summary.cvs == 0
    assert rows_for(sink, CVS_TABLE) == []
    selin = psr_by_id(sink)[SELIN_ID]
    assert selin["keywords"] == ["Autonomous Systems", "Python", "FastAPI", "React"]
    assert selin["cv_url"] == SELIN_CV_URL  # the pointer still comes from the project payload


def test_cursor_records_last_run_at() -> None:
    _summary, _sink, state = run_once()
    cursor = state.load("hacknation")
    assert cursor is not None
    assert cursor.state == {"last_run_at": "2026-07-19T12:00:00+00:00"}


def test_replay_twice_is_byte_identical() -> None:
    _s1, sink_one, _st1 = run_once()
    _s2, sink_two, _st2 = run_once()
    for table in (
        "bronze.hacknation_people_raw",
        "bronze.hacknation_projects_raw",
        CVS_TABLE,
        PSR_TABLE,
        PROJECT_TABLE,
        "bronze._rejects",
    ):
        assert rows_for(sink_one, table) == rows_for(sink_two, table)
