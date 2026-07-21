"""End-to-end fixture replay: the whole WS-A stack over MockTransport, offline.

This is the CI proxy for the G1-G3 acceptance criteria: the 20-repo fixture
set flows through discovery, hydration, contributors, profiles, normalize,
and the runner, with zero credentials and zero network.
"""

from datetime import UTC, date, datetime
from typing import Final

from contracts.models import SinkRow
from scrapers.common.base import RunnerDeps, execute_run
from scrapers.common.http import HttpClient, TokenBucket
from scrapers.common.jsonutil import as_list, as_mapping
from scrapers.common.log import get_logger
from scrapers.common.state import MemoryStateStore
from scrapers.github.client_gql import GithubGraphql
from scrapers.github.client_rest import GithubRest
from scrapers.github.contributors import is_bot
from scrapers.github.replay import fixture_routes
from scrapers.github.scraper import GithubDeps, GithubScraper, NullReadback
from tests.scrapers.conftest import FakeTime, RecordingSink

SINCE: Final[date] = date(2026, 6, 19)
FROZEN_NOW: Final[datetime] = datetime(2026, 7, 19, 12, 0, 0, tzinfo=UTC)
EXPECTED_REPOS: Final[int] = 19  # 20 discovered, one NOT_FOUND at hydration
EXPECTED_COMMITS: Final[int] = 57
EXPECTED_USERS: Final[int] = 10  # ghost-user NOT_FOUND, broken-profile rejected


def build_scraper() -> GithubScraper:
    time = FakeTime()
    log = get_logger("github")
    http = HttpClient(
        user_agent="dealflow-scraper/0.1 (+mailto:test@example.invalid)",
        headers={"Authorization": "Bearer fixture-token"},
        buckets={
            "search": TokenBucket(1000.0, 10.0, timing=time.timing()),
            "core": TokenBucket(1000.0, 10.0, timing=time.timing()),
            "graphql": TokenBucket(1000.0, 10.0, timing=time.timing()),
        },
        transport=fixture_routes(),
        timing=time.timing(),
    )
    return GithubScraper(
        GithubDeps(
            rest=GithubRest(http),
            gql=GithubGraphql(http, log),
            readback=NullReadback(),
            since=SINCE,
            limit=0,
            clock=lambda: FROZEN_NOW,
            run_id="fixture-run",
            log=log,
            explicit_repos=(),
        )
    )


def run_once() -> tuple[RecordingSink, MemoryStateStore, object]:
    sink = RecordingSink()
    state = MemoryStateStore()
    deps = RunnerDeps(sink=sink, state=state, warehouse=None, log=get_logger("github"))
    result = execute_run(build_scraper(), deps, SINCE)
    return sink, state, result


def rows_for(sink: RecordingSink, table: str) -> list[SinkRow]:
    rows: list[SinkRow] = []
    for called_table, called_rows, _keys, _variants in sink.calls:
        if called_table == table:
            rows.extend(called_rows)
    return rows


def test_replay_produces_expected_bronze_counts() -> None:
    sink, _state, result = run_once()
    repos = rows_for(sink, "bronze.github_repos_raw")
    commits = rows_for(sink, "bronze.github_commits_raw")
    users = rows_for(sink, "bronze.github_users_raw")
    rejects = rows_for(sink, "bronze._rejects")
    assert len(repos) == EXPECTED_REPOS
    assert len(commits) == EXPECTED_COMMITS
    assert len(users) == EXPECTED_USERS
    assert len(rejects) == 1
    assert rejects[0]["natural_key"] == "broken-profile"
    assert getattr(result, "items_upserted", None) == EXPECTED_REPOS + EXPECTED_COMMITS + (
        EXPECTED_USERS
    )
    assert getattr(result, "rejects", None) == 1


def test_replay_harvests_zero_bot_logins() -> None:
    sink, _state, _result = run_once()
    for row in rows_for(sink, "bronze.github_users_raw"):
        login = row["login"]
        assert isinstance(login, str)
        assert not is_bot(login, "User")


def test_planted_funded_repo_fires_at_least_two_signals() -> None:
    sink, _state, _result = run_once()
    by_name = {row["full_name"]: row for row in rows_for(sink, "bronze.github_repos_raw")}
    funded = by_name["fx01/proj01"]
    payload = as_mapping(funded["payload"])
    signals = as_list(payload["funded_signals"])
    assert len(signals) >= 2
    assert {"a16z", "backed_by", "org_verified"} <= {str(signal) for signal in signals}


def test_plain_readmes_fire_no_near_miss_signals() -> None:
    sink, _state, _result = run_once()
    for row in rows_for(sink, "bronze.github_repos_raw"):
        if row["full_name"] == "fx01/proj01":
            continue
        assert as_mapping(row["payload"])["funded_signals"] == []


def test_candidate_emails_exclude_noreply_and_carry_sha() -> None:
    sink, _state, _result = run_once()
    by_login = {row["login"]: row for row in rows_for(sink, "bronze.github_users_raw")}
    payload = as_mapping(by_login["dev04"]["payload"])
    assert payload["candidate_emails"] == [{"email": "dev04@example.org", "sha": "0301" * 10}]


def test_commits_carry_stats_and_author_emails() -> None:
    sink, _state, _result = run_once()
    commits = rows_for(sink, "bronze.github_commits_raw")
    with_user_null = [row for row in commits if row["author_user_id"] is None]
    assert len(with_user_null) == 1
    sample = as_mapping(commits[0]["payload"])
    assert isinstance(sample["additions"], int)
    author = as_mapping(sample["author"])
    assert "@" in str(author["email"])


def test_cursor_advances_with_etags_and_watermark() -> None:
    _sink, state, _result = run_once()
    cursor = state.load("github")
    assert cursor is not None
    assert cursor.state["window_end"] == "2026-07-19"
    assert cursor.state["commits_since"] == "2026-07-18T00:00:00Z"
    readme_etags = as_mapping(cursor.state["readme_etags"])
    assert readme_etags["9001"] == 'W/"readme-fx01/proj01"'


def test_replay_twice_is_byte_identical() -> None:
    sink_one, _s1, _r1 = run_once()
    sink_two, _s2, _r2 = run_once()
    for table in (
        "bronze.github_repos_raw",
        "bronze.github_users_raw",
        "bronze.github_commits_raw",
        "bronze._rejects",
    ):
        assert rows_for(sink_one, table) == rows_for(sink_two, table)
