# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""ClaudeCodeLLMClient: completions billed to a Claude Pro/Max subscription.

Headless Claude Code (`claude -p --output-format json`) is the only way to run
programmatic Claude calls against a personal subscription rather than API
credits, so this client shells out to the CLI the operator is already logged
into. It implements contracts.interfaces.LLMClient plus the raw `messages`
surface scoring.deepdive drives, and is selected by LLM_BACKEND=claude-code;
the ANTHROPIC_API_KEY path is untouched and stays the default.

The CLI answers one envelope per call, so the deep dive's pause_turn tool loop
collapses into a single round: Claude Code runs its own built-in WebSearch
while answering, and the emulated body reports those searches back so the
per-venture budget still counts real usage.
"""

import json
import subprocess
from collections.abc import Mapping, Sequence
from typing import Final, Protocol

from contracts.models import Json, LLMResponse
from scrapers.common.jsonutil import as_list, as_mapping, get_int, get_str
from tools.llm import LLMTransportError, UnsupportedLLMOperationError

BACKEND_ENV: Final[str] = "LLM_BACKEND"
CLAUDE_CODE_BACKEND: Final[str] = "claude-code"
DEFAULT_EXECUTABLE: Final[str] = "claude"
# The research tools the deep dive needs; everything that could touch the
# operator's machine stays off, since prompts carry third-party web content.
RESEARCH_TOOLS: Final[tuple[str, ...]] = ("WebSearch", "WebFetch")
DISALLOWED_TOOLS: Final[tuple[str, ...]] = ("Bash", "Edit", "Write", "NotebookEdit", "Task")
CALL_TIMEOUT_SECONDS: Final[float] = 900.0
SCHEMA_INSTRUCTION: Final[str] = (
    "Respond with a single JSON object matching this schema and nothing else "
    "-- no prose, no code fence:\n"
)
TEXT_BLOCK_TYPE: Final[str] = "text"
SERVER_TOOL_USE: Final[str] = "server_tool_use"
WEB_SEARCH_TOOL_NAME: Final[str] = "web_search"
END_TURN: Final[str] = "end_turn"


class CommandRunner(Protocol):
    """The subprocess surface this client needs (subprocess.run fits)."""

    def __call__(self, argv: Sequence[str], stdin_text: str) -> str:
        """Run argv with stdin_text piped in and return stdout."""
        ...


class ClaudeCodeError(LLMTransportError):
    """The Claude Code CLI failed or answered an unusable envelope."""


class ClaudeCodeUnavailableError(ClaudeCodeError):
    """The claude executable is not installed or not on PATH."""

    def __init__(self, executable: str) -> None:
        """Name the executable that could not be run."""
        super().__init__(
            f"{executable!r} is not on PATH; install Claude Code and sign in "
            f"to use {BACKEND_ENV}={CLAUDE_CODE_BACKEND}"
        )


class ClaudeCodeExitError(ClaudeCodeError):
    """The CLI exited non-zero."""

    def __init__(self, returncode: int, stderr: str) -> None:
        """Carry the exit status and whatever the CLI reported."""
        detail = stderr.strip() or "no stderr"
        super().__init__(f"claude exited {returncode}: {detail}")


class ClaudeCodeTimeoutError(ClaudeCodeError):
    """The CLI did not answer within the call timeout."""

    def __init__(self, seconds: float) -> None:
        """Carry the elapsed budget in the message."""
        super().__init__(f"claude timed out after {seconds:.0f}s")


class ClaudeCodeEnvelopeError(ClaudeCodeError):
    """The CLI answered something other than a success envelope."""

    def __init__(self, reason: str) -> None:
        """Explain what was wrong with the envelope."""
        super().__init__(f"claude returned an unusable envelope: {reason}")


class UnreadableEnvelopeError(ClaudeCodeEnvelopeError):
    """Stdout was not JSON at all (a crash or a usage notice, typically)."""

    def __init__(self) -> None:
        """State that stdout never parsed."""
        super().__init__("stdout is not JSON")


class MissingResultError(ClaudeCodeEnvelopeError):
    """The envelope parsed but carried no result text."""

    def __init__(self) -> None:
        """State that the result field was absent or mistyped."""
        super().__init__("no result string")


class SchemaResponseError(ClaudeCodeEnvelopeError):
    """A schema-constrained completion did not come back as a JSON object."""

    def __init__(self, *, decoded: bool) -> None:
        """Distinguish unparseable output from a non-object value."""
        super().__init__(
            "schema was requested but the answer is not an object"
            if decoded
            else "schema was requested but the answer is not JSON"
        )


def _run_subprocess(argv: Sequence[str], stdin_text: str) -> str:
    try:
        completed = subprocess.run(  # noqa: S603 - argv is built here, never shell-interpolated
            list(argv),
            input=stdin_text,
            capture_output=True,
            text=True,
            timeout=CALL_TIMEOUT_SECONDS,
            check=False,
        )
    except FileNotFoundError as error:
        raise ClaudeCodeUnavailableError(argv[0]) from error
    except subprocess.TimeoutExpired as error:
        raise ClaudeCodeTimeoutError(CALL_TIMEOUT_SECONDS) from error
    if completed.returncode != 0:
        raise ClaudeCodeExitError(completed.returncode, completed.stderr)
    return completed.stdout


def _envelope_text(stdout: str) -> tuple[str, dict[str, Json]]:
    """The CLI envelope's result text and usage block.

    Args:
        stdout: Raw CLI stdout.

    Returns:
        The result text and the usage mapping (empty when absent).

    Raises:
        ClaudeCodeEnvelopeError: If the CLI reported an error in the envelope.
        UnreadableEnvelopeError: If stdout is not JSON.
        MissingResultError: If the envelope carries no result text.
    """
    try:
        decoded: object = json.loads(stdout)
    except json.JSONDecodeError as error:
        raise UnreadableEnvelopeError from error
    envelope = as_mapping(decoded)
    if envelope.get("is_error"):
        raise ClaudeCodeEnvelopeError(get_str(envelope, "result") or "is_error was set")
    result = envelope.get("result")
    if not isinstance(result, str):
        raise MissingResultError
    return result, as_mapping(envelope.get("usage"))


def _strip_fence(text: str) -> str:
    """The body of a ```json fence, or the text unchanged when unfenced."""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _web_searches(usage: dict[str, Json]) -> int:
    return get_int(as_mapping(usage.get(SERVER_TOOL_USE)), "web_search_requests") or 0


def _flatten(messages: Sequence[Json]) -> str:
    """One prompt from a Messages-API conversation.

    The CLI takes a single prompt, so an assistant turn carried back by the
    deep dive's loop is re-rendered as labelled transcript text.
    """
    parts: list[str] = []
    for message in messages:
        entry = as_mapping(message)
        role = get_str(entry, "role") or "user"
        content = entry.get("content")
        if isinstance(content, str):
            body = content
        else:
            body = "\n".join(
                text
                for block in as_list(content)
                if as_mapping(block).get("type") == TEXT_BLOCK_TYPE
                and isinstance(text := as_mapping(block).get("text"), str)
            )
        if body:
            parts.append(body if role == "user" else f"[{role}]\n{body}")
    return "\n\n".join(parts)


class ClaudeCodeLLMClient:
    """LLMClient backed by headless Claude Code (subscription-billed)."""

    def __init__(
        self,
        *,
        model: str | None = None,
        executable: str = DEFAULT_EXECUTABLE,
        runner: CommandRunner | None = None,
        allow_research: bool = True,
    ) -> None:
        """Bind the CLI invocation; a runner replaces the subprocess in tests.

        Args:
            model: Model passed through to --model; the CLI default when None.
            executable: The claude binary name or path.
            runner: Command runner; defaults to a real subprocess call.
            allow_research: Permit the built-in WebSearch/WebFetch tools, which
                is what lets the deep dive research on the subscription.
        """
        self._model: Final[str | None] = model
        self._executable: Final[str] = executable
        self._runner: Final[CommandRunner] = runner or _run_subprocess
        self._allow_research: Final[bool] = allow_research

    def _argv(self, *, model: str | None, tools: bool) -> list[str]:
        argv = [self._executable, "-p", "--output-format", "json"]
        chosen = model or self._model
        if chosen is not None:
            argv += ["--model", chosen]
        if tools and self._allow_research:
            argv += ["--allowed-tools", *RESEARCH_TOOLS]
        argv += ["--disallowed-tools", *DISALLOWED_TOOLS]
        return argv

    def complete(
        self,
        prompt: str,
        *,
        schema: Mapping[str, Json] | None = None,
        model: str | None = None,
    ) -> LLMResponse:
        """Run one completion through the CLI.

        Args:
            prompt: The prompt text, piped in on stdin.
            schema: When given, the prompt demands a single JSON object and the
                answer is parsed into `parsed`.
            model: Model override for this call.

        Returns:
            The completion; with a schema, `text` is the canonical JSON
            rendering of `parsed`, matching AnthropicHttpClient.

        Raises:
            SchemaResponseError: If a schema was requested and the answer did
                not parse as a JSON object.
        """
        stdin_text = prompt
        if schema is not None:
            stdin_text = (
                f"{prompt}\n\n{SCHEMA_INSTRUCTION}{json.dumps(dict(schema), sort_keys=True)}"
            )
        stdout = self._runner(self._argv(model=model, tools=False), stdin_text)
        result, _ = _envelope_text(stdout)
        if schema is None:
            return LLMResponse(
                text=result, parsed=None, model=model or self._model or "claude-code"
            )
        try:
            decoded: object = json.loads(_strip_fence(result))
        except json.JSONDecodeError as error:
            raise SchemaResponseError(decoded=False) from error
        parsed = as_mapping(decoded)
        if not parsed:
            raise SchemaResponseError(decoded=True)
        return LLMResponse(
            text=json.dumps(parsed, sort_keys=True),
            parsed=parsed,
            model=model or self._model or "claude-code",
        )

    def messages(self, payload: Mapping[str, Json]) -> dict[str, Json]:
        """Answer one raw Messages-API request through the CLI.

        The conversation is flattened into a single prompt and Claude Code does
        its own web research, so the reply always ends the turn. Each search it
        actually ran is reported back as a server_tool_use block, which is what
        the deep dive counts against the per-venture budget.

        Args:
            payload: A Messages request body (model/messages/tools/...).

        Returns:
            A Messages-shaped body with one text block.
        """
        request = as_mapping(payload)
        prompt = _flatten(as_list(request.get("messages")))
        stdout = self._runner(self._argv(model=get_str(request, "model"), tools=True), prompt)
        result, usage = _envelope_text(stdout)
        content: list[Json] = [
            {"type": SERVER_TOOL_USE, "name": WEB_SEARCH_TOOL_NAME}
            for _ in range(_web_searches(usage))
        ]
        content.append({"type": TEXT_BLOCK_TYPE, "text": _strip_fence(result)})
        return {
            "content": content,
            "stop_reason": END_TURN,
            "usage": {
                "input_tokens": get_int(usage, "input_tokens") or 0,
                "output_tokens": get_int(usage, "output_tokens") or 0,
            },
        }

    def embed(self, text: str) -> list[float]:
        """Claude Code has no embeddings surface.

        Args:
            text: Ignored.

        Returns:
            Never returns.

        Raises:
            UnsupportedLLMOperationError: Always.
        """
        del text
        raise UnsupportedLLMOperationError("ClaudeCodeLLMClient", "embed")
