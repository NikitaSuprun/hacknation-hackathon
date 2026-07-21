"""Deep dive: scripted transports, the 12-search cap, weekly cache, run log."""

import json
from collections.abc import Mapping
from typing import Final

import pytest

from contracts.models import CategoryScore, Json, VentureView
from fixtures import build
from scoring.deepdive import (
    MAX_SEARCHES_PER_VENTURE,
    DeepDiveAgent,
    SearchBudgetExceededError,
    iso_week,
)
from scoring.runlog import LLM_RUN_LOG_TABLE, RunLog, run_log_keys
from scoring.scripted import FIXTURE_NOW
from scrapers.common.sink import NullSink

VENTURE: Final[VentureView] = VentureView(
    venture_id=build.GRASP_VENTURE,
    name="GraspLab",
    one_liner="Foundation models for robotic grasping",
    anchor_type="repo",
    member_person_ids=(build.LENA, build.WEI_A),
    extras={},
)


def verdict_body(searches: int, score: float) -> dict[str, Json]:
    answer = {
        "score": score,
        "confidence": 0.7,
        "rationale": "web evidence",
        "evidence": [
            {"claim": "corroborated claim", "source_url": "https://news.ycombinator.com/item?id=1"}
        ],
    }
    content: list[Json] = [
        {"type": "server_tool_use", "name": "web_search", "id": f"s{i}", "input": {}}
        for i in range(searches)
    ]
    content.append({"type": "text", "text": json.dumps(answer)})
    return {
        "content": content,
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 1000, "output_tokens": 200},
    }


class FakeMessages:
    """A scripted Messages transport recording every request payload."""

    def __init__(self, bodies: list[dict[str, Json]]) -> None:
        self.bodies: list[dict[str, Json]] = list(bodies)
        self.calls: list[dict[str, Json]] = []

    def messages(self, payload: Mapping[str, Json]) -> dict[str, Json]:
        self.calls.append(dict(payload))
        return self.bodies.pop(0)


def agent_for(client: FakeMessages, run_log: RunLog) -> DeepDiveAgent:
    cache: dict[tuple[str, str, str], CategoryScore] = {}
    return DeepDiveAgent(client, cache, run_log, lambda: FIXTURE_NOW)


def run_log_for(sink: NullSink) -> RunLog:
    return RunLog(sink, "run-test", lambda: FIXTURE_NOW)


def test_four_categories_scored_with_url_cited_evidence() -> None:
    client = FakeMessages([verdict_body(2, 70.0) for _ in range(4)])
    sink = NullSink()
    run_log = run_log_for(sink)
    results = agent_for(client, run_log).score_venture(VENTURE)
    assert set(results) == {"problem_realness", "market", "traction", "network_ties"}
    for verdict in results.values():
        assert verdict.score == 70.0
        assert verdict.method == "web_agent"
        assert verdict.evidence
        assert verdict.evidence[0].source_url.startswith("https://")
    assert len(run_log.rows) == 4
    assert all(row["searches"] == 2 for row in run_log.rows)
    costs = [row["cost_usd"] for row in run_log.rows]
    assert all(isinstance(cost, float) and 0.0 < cost < 1.0 for cost in costs)


def test_run_log_flushes_with_registry_fallback_keys() -> None:
    sink = NullSink()
    run_log = run_log_for(sink)
    client = FakeMessages([verdict_body(1, 60.0) for _ in range(4)])
    agent_for(client, run_log).score_venture(VENTURE)
    result = run_log.flush()
    assert result is not None
    assert result.table == LLM_RUN_LOG_TABLE
    assert sink.rows[LLM_RUN_LOG_TABLE]
    assert run_log_keys() == ["run_id", "stage"]  # ops.llm_run_log has no PK


def test_thirteenth_search_is_refused() -> None:
    # Three categories consume the full budget of 12; the fourth would need
    # a 13th search and comes back as a low-confidence N/A verdict.
    client = FakeMessages([verdict_body(4, 70.0) for _ in range(3)])
    run_log = run_log_for(NullSink())
    results = agent_for(client, run_log).score_venture(VENTURE)
    exhausted = results["network_ties"]
    assert exhausted.score is None
    assert exhausted.rationale is not None
    assert "budget" in exhausted.rationale
    assert len(client.calls) == 3  # the fourth request was never sent


def test_request_beyond_cap_raises() -> None:
    client = FakeMessages([])
    agent = agent_for(client, run_log_for(NullSink()))
    with pytest.raises(SearchBudgetExceededError, match=str(MAX_SEARCHES_PER_VENTURE)):
        agent._request(VENTURE.venture_id, [], MAX_SEARCHES_PER_VENTURE)  # pyright: ignore[reportPrivateUsage] - cap check is internal by design


def test_max_uses_shrinks_with_the_remaining_budget() -> None:
    client = FakeMessages([verdict_body(5, 70.0), verdict_body(5, 70.0), verdict_body(2, 70.0)])
    run_log = run_log_for(NullSink())
    agent_for(client, run_log).score_venture(VENTURE)
    tools = [call["tools"] for call in client.calls]
    max_uses: list[Json] = []
    for entry in tools:
        assert isinstance(entry, list)
        first = entry[0]
        assert isinstance(first, dict)
        max_uses.append(first["max_uses"])
    assert max_uses == [12, 7, 2]


def test_weekly_cache_skips_the_transport() -> None:
    week = iso_week(FIXTURE_NOW)
    cached = CategoryScore(
        category="market",
        score=68.0,
        confidence=0.7,
        method="web_agent",
        rationale="cached",
        evidence=(),
    )
    cache = {
        (VENTURE.venture_id, category, week): cached
        for category in ("problem_realness", "market", "traction", "network_ties")
    }
    client = FakeMessages([])
    run_log = run_log_for(NullSink())
    agent = DeepDiveAgent(client, cache, run_log, lambda: FIXTURE_NOW)
    results = agent.score_venture(VENTURE)
    assert client.calls == []
    assert run_log.rows == []
    assert results["market"].rationale == "cached"


def test_pause_turn_continues_the_loop() -> None:
    paused = verdict_body(3, 70.0)
    paused["stop_reason"] = "pause_turn"
    bodies = [paused, verdict_body(1, 70.0)]
    bodies.extend(verdict_body(0, 50.0) for _ in range(3))
    client = FakeMessages(bodies)
    run_log = run_log_for(NullSink())
    results = agent_for(client, run_log).score_venture(VENTURE)
    assert results["problem_realness"].score == 70.0
    first_row = run_log.rows[0]
    assert first_row["searches"] == 4  # 3 before the pause + 1 after
