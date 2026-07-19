# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""LLMClient implementations: scripting, ai_query SQL, Anthropic transport."""

import json
from typing import Final

import httpx
import pytest

from contracts.models import LLMResponse
from fixtures.fake_embedding import EMBEDDING_DIM, fake_embedding
from tools.llm import (
    AiQueryLLMClient,
    AnthropicHttpClient,
    LLMTransportError,
    ScriptedLLMClient,
    UnknownPromptError,
    UnsupportedLLMOperationError,
    prompt_tag,
)

VERDICT: Final[LLMResponse] = LLMResponse(
    text='{"verdict": "match"}', parsed={"verdict": "match"}, model="scripted"
)


class FakeRunner:
    """A SqlRunner answering canned rows and recording statements."""

    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        """Store the canned rows."""
        self.rows: Final[list[tuple[object, ...]]] = rows
        self.statements: Final[list[str]] = []

    def execute(self, statement: str) -> list[tuple[object, ...]]:
        """Record the statement and return the canned rows."""
        self.statements.append(statement)
        return self.rows


def test_prompt_tag_is_first_line() -> None:
    assert prompt_tag("TASK:adjudicate pair=p1\nRecord A: ...") == "TASK:adjudicate pair=p1"
    assert prompt_tag("") == ""


def test_scripted_client_matches_on_tag_and_records_calls() -> None:
    client = ScriptedLLMClient({"TASK:adjudicate pair=p1": VERDICT}, embedder=fake_embedding)
    response = client.complete("TASK:adjudicate pair=p1\nRecord A: x Record B: y")
    assert response.parsed == {"verdict": "match"}
    assert client.calls == ["TASK:adjudicate pair=p1"]


def test_scripted_client_unknown_tag_raises_without_default() -> None:
    client = ScriptedLLMClient({}, embedder=fake_embedding)
    with pytest.raises(UnknownPromptError, match="TASK:missing"):
        client.complete("TASK:missing\nbody")


def test_scripted_client_default_covers_unmatched_tags() -> None:
    client = ScriptedLLMClient({}, embedder=fake_embedding, default=VERDICT)
    assert client.complete("TASK:anything").text == '{"verdict": "match"}'


def test_scripted_embed_is_fake_embedding() -> None:
    client = ScriptedLLMClient({}, embedder=fake_embedding)
    vector = client.embed("robotics")
    assert vector == fake_embedding("robotics")
    assert len(vector) == EMBEDDING_DIM


def test_ai_query_complete_sql_is_golden_and_escaped() -> None:
    runner = FakeRunner([('{"score": 80}',)])
    client = AiQueryLLMClient(runner)
    response = client.complete("It's a test", schema={"type": "object"})
    assert runner.statements == ["SELECT ai_query('databricks-claude-sonnet-4-6', 'It''s a test')"]
    assert response.parsed == {"score": 80}
    assert response.model == "databricks-claude-sonnet-4-6"


def test_ai_query_without_schema_leaves_parsed_none() -> None:
    client = AiQueryLLMClient(
        FakeRunner([("plain text",)]), default_model="databricks-claude-haiku-4-5"
    )
    response = client.complete("TASK:x")
    assert response.text == "plain text"
    assert response.parsed is None
    assert response.model == "databricks-claude-haiku-4-5"


def test_ai_query_empty_result_raises_transport_error() -> None:
    client = AiQueryLLMClient(FakeRunner([]))
    with pytest.raises(LLMTransportError, match="returned no row"):
        client.complete("TASK:x")


def test_ai_query_embed_normalizes_and_checks_dims() -> None:
    raw = [3.0] + [0.0] * (EMBEDDING_DIM - 2) + [4.0]
    client = AiQueryLLMClient(FakeRunner([(json.dumps(raw),)]))
    vector = client.embed("text")
    assert len(vector) == EMBEDDING_DIM
    assert vector[0] == pytest.approx(0.6)
    assert vector[-1] == pytest.approx(0.8)
    bad = AiQueryLLMClient(FakeRunner([("[1.0, 2.0]",)]))
    with pytest.raises(LLMTransportError, match="dims"):
        bad.embed("text")


def anthropic_client(handler: httpx.MockTransport) -> AnthropicHttpClient:
    return AnthropicHttpClient("test-key", transport=handler)


def test_anthropic_schema_forces_tool_and_parses_input() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={"content": [{"type": "tool_use", "name": "emit", "input": {"verdict": "match"}}]},
        )

    client = anthropic_client(httpx.MockTransport(handler))
    response = client.complete("TASK:adjudicate", schema={"type": "object"})
    assert response.parsed == {"verdict": "match"}
    assert response.text == '{"verdict": "match"}'
    body = json.loads(seen[0].content)
    assert body["tool_choice"] == {"type": "tool", "name": "emit"}
    assert body["tools"][0]["input_schema"] == {"type": "object"}
    assert seen[0].headers["x-api-key"] == "test-key"
    assert seen[0].headers["anthropic-version"] == "2023-06-01"


def test_anthropic_plain_completion_joins_text_blocks() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            200,
            json={
                "content": [{"type": "text", "text": "Hello "}, {"type": "text", "text": "world"}]
            },
        )

    client = anthropic_client(httpx.MockTransport(handler))
    assert client.complete("hi").text == "Hello world"


def test_anthropic_error_status_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(429)

    client = anthropic_client(httpx.MockTransport(handler))
    with pytest.raises(LLMTransportError, match="HTTP 429"):
        client.complete("hi")


def test_anthropic_embed_is_unsupported() -> None:
    client = anthropic_client(httpx.MockTransport(lambda _r: httpx.Response(200, json={})))
    with pytest.raises(UnsupportedLLMOperationError, match="embed"):
        client.embed("text")
