"""ClaudeCodeLLMClient: CLI argv surface, envelope parsing, Messages emulation."""

import json
import stat
from collections.abc import Sequence
from pathlib import Path
from typing import Final

import pytest

from contracts.models import Json
from scoring.deps import build_scoring_deps
from tools.llm_cli import (
    ClaudeCodeEnvelopeError,
    ClaudeCodeExitError,
    ClaudeCodeLLMClient,
    ClaudeCodeUnavailableError,
    UnsupportedLLMOperationError,
)
from tools.settings import MissingConfigError

SCHEMA: Final[dict[str, Json]] = {
    "type": "object",
    "properties": {"score": {"type": "number"}},
}


class FakeRunner:
    """A CommandRunner answering a canned envelope and recording its calls."""

    def __init__(self, stdout: str) -> None:
        """Bind the stdout every call returns."""
        self.stdout: Final[str] = stdout
        self.argv: list[Sequence[str]] = []
        self.stdin: list[str] = []

    def __call__(self, argv: Sequence[str], stdin_text: str) -> str:
        """Record the invocation and answer the canned stdout."""
        self.argv.append(list(argv))
        self.stdin.append(stdin_text)
        return self.stdout


def envelope(result: str, **extra: Json) -> str:
    """One CLI success envelope as the real `claude --output-format json` emits."""
    body: dict[str, Json] = {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "result": result,
        "usage": {"input_tokens": 11, "output_tokens": 22},
    }
    body.update(extra)
    return json.dumps(body)


def test_plain_completion_pipes_the_prompt_and_returns_the_result() -> None:
    runner = FakeRunner(envelope("pong"))
    client = ClaudeCodeLLMClient(runner=runner)

    response = client.complete("ping")

    assert response.text == "pong"
    assert response.parsed is None
    assert runner.stdin == ["ping"]
    argv = runner.argv[0]
    assert argv[:4] == ["claude", "-p", "--output-format", "json"]


def test_plain_completion_never_offers_tools() -> None:
    runner = FakeRunner(envelope("pong"))

    ClaudeCodeLLMClient(runner=runner).complete("ping")

    assert "--allowed-tools" not in runner.argv[0]
    assert "--disallowed-tools" in runner.argv[0]


def test_model_override_reaches_the_cli() -> None:
    runner = FakeRunner(envelope("pong"))
    client = ClaudeCodeLLMClient(model="claude-opus-4-8", runner=runner)

    client.complete("ping", model="claude-sonnet-5")

    argv = list(runner.argv[0])
    assert argv[argv.index("--model") + 1] == "claude-sonnet-5"


def test_schema_completion_parses_and_canonicalizes() -> None:
    runner = FakeRunner(envelope('{"score": 0.5}'))
    client = ClaudeCodeLLMClient(runner=runner)

    response = client.complete("rate it", schema=SCHEMA)

    assert response.parsed == {"score": 0.5}
    assert response.text == '{"score": 0.5}'
    assert "single JSON object" in runner.stdin[0]


def test_schema_completion_tolerates_a_code_fence() -> None:
    runner = FakeRunner(envelope('```json\n{"score": 0.25}\n```'))

    response = ClaudeCodeLLMClient(runner=runner).complete("rate it", schema=SCHEMA)

    assert response.parsed == {"score": 0.25}


def test_schema_completion_rejects_prose() -> None:
    client = ClaudeCodeLLMClient(runner=FakeRunner(envelope("I think it is fine")))

    with pytest.raises(ClaudeCodeEnvelopeError):
        client.complete("rate it", schema=SCHEMA)


def test_error_envelope_is_surfaced() -> None:
    runner = FakeRunner(json.dumps({"is_error": True, "result": "usage limit reached"}))

    with pytest.raises(ClaudeCodeEnvelopeError, match="usage limit"):
        ClaudeCodeLLMClient(runner=runner).complete("ping")


def test_non_json_stdout_is_surfaced() -> None:
    with pytest.raises(ClaudeCodeEnvelopeError, match="not JSON"):
        ClaudeCodeLLMClient(runner=FakeRunner("command not found")).complete("ping")


def test_messages_returns_a_terminal_messages_body() -> None:
    runner = FakeRunner(envelope('{"score": 0.8, "rationale": "strong"}'))
    client = ClaudeCodeLLMClient(runner=runner)

    body = client.messages(
        {"model": "claude-opus-4-8", "messages": [{"role": "user", "content": "research this"}]}
    )

    # The deep dive's loop only stops on a non-pause_turn stop_reason.
    assert body["stop_reason"] == "end_turn"
    assert body["usage"] == {"input_tokens": 11, "output_tokens": 22}
    blocks = body["content"]
    assert isinstance(blocks, list)
    assert blocks[-1] == {"type": "text", "text": '{"score": 0.8, "rationale": "strong"}'}
    assert runner.stdin == ["research this"]


def test_messages_allows_research_tools() -> None:
    runner = FakeRunner(envelope("{}"))

    ClaudeCodeLLMClient(runner=runner).messages({"messages": []})

    argv = list(runner.argv[0])
    assert argv[argv.index("--allowed-tools") + 1] == "WebSearch"


def test_messages_reports_searches_so_the_budget_still_counts() -> None:
    runner = FakeRunner(
        envelope(
            "{}",
            usage={
                "input_tokens": 3,
                "output_tokens": 4,
                "server_tool_use": {"web_search_requests": 2},
            },
        )
    )

    body = ClaudeCodeLLMClient(runner=runner).messages({"messages": []})

    blocks = body["content"]
    assert isinstance(blocks, list)
    searches = [block for block in blocks if isinstance(block, dict) and block["type"] != "text"]
    assert searches == [{"type": "server_tool_use", "name": "web_search"}] * 2


def test_messages_flattens_an_assistant_turn_back_into_the_prompt() -> None:
    runner = FakeRunner(envelope("{}"))

    ClaudeCodeLLMClient(runner=runner).messages(
        {
            "messages": [
                {"role": "user", "content": "first"},
                {"role": "assistant", "content": [{"type": "text", "text": "second"}]},
            ]
        }
    )

    assert runner.stdin == ["first\n\n[assistant]\nsecond"]


def test_embed_is_unsupported() -> None:
    with pytest.raises(UnsupportedLLMOperationError):
        ClaudeCodeLLMClient(runner=FakeRunner(envelope("x"))).embed("text")


def test_missing_executable_names_the_backend(tmp_path: Path) -> None:
    client = ClaudeCodeLLMClient(executable=str(tmp_path / "definitely-not-installed"))

    with pytest.raises(ClaudeCodeUnavailableError, match="LLM_BACKEND=claude-code"):
        client.complete("ping")


def test_real_subprocess_reads_stdin_and_parses_the_envelope(tmp_path: Path) -> None:
    """The default runner drives a real process, not just the injected fake."""
    stub = tmp_path / "claude"
    stub.write_text(
        "#!/bin/sh\n"
        'prompt="$(cat)"\n'
        'printf \'{"is_error": false, "result": "%s", "usage": {}}\\n\' "$prompt"\n',
        encoding="utf-8",
    )
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)

    response = ClaudeCodeLLMClient(executable=str(stub)).complete("echoed")

    assert response.text == "echoed"


def test_real_subprocess_reports_a_non_zero_exit(tmp_path: Path) -> None:
    stub = tmp_path / "claude"
    stub.write_text("#!/bin/sh\necho 'not logged in' >&2\nexit 3\n", encoding="utf-8")
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)

    with pytest.raises(ClaudeCodeExitError, match="not logged in"):
        ClaudeCodeLLMClient(executable=str(stub)).complete("ping")


def test_backend_env_selects_the_client_without_an_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_BACKEND", "claude-code")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    deps = build_scoring_deps(fixtures=False, dry_run=True, stage_b=True)

    assert isinstance(deps.llm, ClaudeCodeLLMClient)


def test_backend_env_unset_still_demands_the_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_BACKEND", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    with pytest.raises(MissingConfigError):
        build_scoring_deps(fixtures=False, dry_run=True, stage_b=True)
