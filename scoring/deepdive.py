"""Stage-B deep dive: Opus + web_search under hard caps, cached weekly.

Drives the raw Messages API (AnthropicHttpClient.messages) in a tool loop:
the server executes web searches, the loop continues on pause_turn, and every
server_tool_use block counts against MAX_SEARCHES_PER_VENTURE. Exhausting the
budget is a valid outcome — the category comes back low-confidence instead of
burning money. Results cache per (venture, category, ISO week) and land in
ops.llm_run_log with searches and estimated cost.
"""

import json
from collections.abc import Callable, Mapping, MutableMapping
from datetime import datetime
from typing import Final, Protocol

from contracts.models import CategoryScore, Evidence, Json, VentureView
from scoring.categories.stage_b import STAGE_B_CATEGORIES
from scoring.runlog import LlmUsage, RunLog
from scoring.snapshot import get_float
from scrapers.common.jsonutil import as_list, as_mapping, get_int, get_list, get_str
from tools.llm import DEFAULT_ANTHROPIC_MODEL, DEFAULT_MAX_TOKENS

MAX_SEARCHES_PER_VENTURE: Final[int] = 12
STAGE_B_TOP_K: Final[int] = 25
WEB_SEARCH_TOOL_TYPE: Final[str] = "web_search_20250305"
WEB_SEARCH_TOOL_NAME: Final[str] = "web_search"
SERVER_TOOL_USE: Final[str] = "server_tool_use"
PAUSE_TURN: Final[str] = "pause_turn"
MAX_LOOP_ROUNDS: Final[int] = 8

COST_PER_SEARCH_USD: Final[float] = 0.01
INPUT_COST_PER_MTOK_USD: Final[float] = 15.0
OUTPUT_COST_PER_MTOK_USD: Final[float] = 75.0


class SearchBudgetExceededError(RuntimeError):
    """The per-venture web-search budget is exhausted."""

    def __init__(self, venture_id: str) -> None:
        """Name the venture whose budget ran out."""
        super().__init__(
            f"web-search budget ({MAX_SEARCHES_PER_VENTURE}) exhausted for {venture_id}"
        )


class MessagesClient(Protocol):
    """The raw Messages-API surface the agent drives (AnthropicHttpClient fits)."""

    def messages(self, payload: Mapping[str, Json]) -> dict[str, Json]:
        """Send one raw Messages request and return the decoded body."""
        ...


type CacheKey = tuple[str, str, str]
"""(venture_id, category, ISO week)."""


def iso_week(now: datetime) -> str:
    """The cache-bucketing ISO week label.

    Args:
        now: The injected clock value.

    Returns:
        e.g. '2026-W29'.
    """
    return now.strftime("%G-W%V")


def _count_searches(body: dict[str, Json]) -> int:
    return sum(
        1
        for block in as_list(body.get("content"))
        if as_mapping(block).get("type") == SERVER_TOOL_USE
        and as_mapping(block).get("name") == WEB_SEARCH_TOOL_NAME
    )


def _usage_tokens(body: dict[str, Json]) -> tuple[int, int]:
    usage = as_mapping(body.get("usage"))
    return get_int(usage, "input_tokens") or 0, get_int(usage, "output_tokens") or 0


def _final_text(body: dict[str, Json]) -> str:
    parts = [
        text
        for block in as_list(body.get("content"))
        if as_mapping(block).get("type") == "text"
        and isinstance(text := as_mapping(block).get("text"), str)
    ]
    return "".join(parts)


def _parse_verdict(category: str, body: dict[str, Json]) -> CategoryScore:
    text = _final_text(body)
    try:
        decoded: object = json.loads(text)
    except json.JSONDecodeError:
        decoded = None
    parsed = as_mapping(decoded)
    evidence: list[Evidence] = []
    for item in get_list(parsed, "evidence"):
        entry = as_mapping(item)
        claim = get_str(entry, "claim")
        url = get_str(entry, "source_url")
        if claim and url:
            evidence.append(
                Evidence(
                    claim=claim,
                    source_url=url,
                    source_type=get_str(entry, "source_type") or "web",
                    snippet=get_str(entry, "snippet"),
                    weight=None,
                )
            )
    return CategoryScore(
        category=category,
        score=get_float(parsed, "score"),
        confidence=get_float(parsed, "confidence") or (0.6 if evidence else 0.3),
        method="web_agent",
        rationale=get_str(parsed, "rationale"),
        evidence=tuple(evidence),
    )


def _category_prompt(venture: VentureView, category: str) -> str:
    return (
        f"TASK:deep_dive venture={venture.venture_id} category={category}\n"
        f"Venture: {venture.name} - {venture.one_liner or 'unknown'}\n"
        "Search the web, then answer as one JSON object "
        '{"score": 0-100 or null, "confidence": 0-1, "rationale": str, '
        '"evidence": [{"claim": str, "source_url": str}]} '
        "citing verbatim URLs from the search results."
    )


class DeepDiveAgent:
    """The capped, cached web-search loop over the four Stage-B categories."""

    def __init__(
        self,
        client: MessagesClient,
        cache: MutableMapping[CacheKey, CategoryScore],
        run_log: RunLog,
        clock: Callable[[], datetime],
        model: str = DEFAULT_ANTHROPIC_MODEL,
    ) -> None:
        """Bind the transport, the weekly cache, spend logging, and the clock."""
        self._client: Final[MessagesClient] = client
        self._cache: Final[MutableMapping[CacheKey, CategoryScore]] = cache
        self._run_log: Final[RunLog] = run_log
        self._clock: Final[Callable[[], datetime]] = clock
        self._model: Final[str] = model

    def _request(self, venture_id: str, messages: list[Json], used: int) -> dict[str, Json]:
        remaining = MAX_SEARCHES_PER_VENTURE - used
        if remaining <= 0:
            raise SearchBudgetExceededError(venture_id)
        payload: dict[str, Json] = {
            "model": self._model,
            "max_tokens": DEFAULT_MAX_TOKENS,
            "messages": list(messages),
            "tools": [
                {
                    "type": WEB_SEARCH_TOOL_TYPE,
                    "name": WEB_SEARCH_TOOL_NAME,
                    "max_uses": remaining,
                }
            ],
        }
        return self._client.messages(payload)

    def _run_category(
        self, venture: VentureView, category: str, used: int
    ) -> tuple[CategoryScore, int, LlmUsage]:
        messages: list[Json] = [{"role": "user", "content": _category_prompt(venture, category)}]
        searches = 0
        input_tokens = 0
        output_tokens = 0
        body: dict[str, Json] = {}
        for _ in range(MAX_LOOP_ROUNDS):
            body = self._request(venture.venture_id, messages, used + searches)
            searches += _count_searches(body)
            tokens_in, tokens_out = _usage_tokens(body)
            input_tokens += tokens_in
            output_tokens += tokens_out
            if body.get("stop_reason") != PAUSE_TURN:
                break
            messages.append({"role": "assistant", "content": body.get("content")})
        cost = (
            searches * COST_PER_SEARCH_USD
            + input_tokens / 1e6 * INPUT_COST_PER_MTOK_USD
            + output_tokens / 1e6 * OUTPUT_COST_PER_MTOK_USD
        )
        usage = LlmUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            searches=searches,
            cost_usd=round(cost, 4),
        )
        return _parse_verdict(category, body), used + searches, usage

    def score_venture(self, venture: VentureView) -> dict[str, CategoryScore]:
        """Deep-dive the four Stage-B categories for one venture.

        Args:
            venture: The venture to research.

        Returns:
            Verdicts keyed by category; budget exhaustion yields a
            low-confidence N/A verdict instead of an exception.
        """
        week = iso_week(self._clock())
        results: dict[str, CategoryScore] = {}
        used = 0
        for category in STAGE_B_CATEGORIES:
            key: CacheKey = (venture.venture_id, category, week)
            cached = self._cache.get(key)
            if cached is not None:
                results[category] = cached
                continue
            try:
                verdict, used, usage = self._run_category(venture, category, used)
            except SearchBudgetExceededError:
                results[category] = CategoryScore(
                    category=category,
                    score=None,
                    confidence=0.2,
                    method="web_agent",
                    rationale="web-search budget exhausted before this category",
                    evidence=(),
                )
                continue
            self._run_log.record(f"stage_b:{category}", self._model, usage)
            self._cache[key] = verdict
            results[category] = verdict
        return results
